"""Verification orchestration service.

Validates the upload, stores it safely, extracts signals, builds features,
runs the ML model, builds the certificate-intelligence layer, detects
duplicates, and persists the result.
"""

import json
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ModelUnavailableError, ProcessingError
from app.core.logging import get_logger
from app.models.certificate import Certificate
from app.models.verification import Verification
from app.ml import model as model_service
from app.services.consistency_service import build_consistency_findings
from app.services.duplicate_service import (
    cert_id_fingerprint,
    file_fingerprint,
    find_duplicate,
    identity_fingerprint,
)
from app.services.extraction_service import extract_document
from app.services.feature_service import build_features_from_extraction
from app.services.file_service import delete_upload, save_upload
from app.services.intelligence_service import (
    build_intelligence,
    build_signals,
    compute_review_status,
    recommended_action,
)
from app.services.ood_service import compute_ood_status
from app.services.priority_service import compute_review_priority
from app.services.phase12_pipeline import run_phase12_pipeline
from app.services import audit_service
from app.utils.file_utils import validate_file

logger = get_logger("verification_service")

GENUINE_MESSAGE = (
    "AI-based preliminary verification: no strong fraud-risk signals were "
    "found. This is a preliminary automated result, not a legal authenticity "
    "guarantee."
)
SUSPICIOUS_MESSAGE = (
    "AI-based preliminary verification: the document shows signals commonly "
    "associated with potentially fraudulent certificates. Manual review is "
    "strongly recommended."
)
REQUIRES_VERIFICATION_MESSAGE = (
    "AI-based preliminary verification: the document is structurally "
    "consistent, but the evidence is contradictory or incomplete (for example, "
    "credential identifiers that could not be confirmed against the issuer). "
    "Manual review is recommended."
)
INSUFFICIENT_EVIDENCE_MESSAGE = (
    "AI-based preliminary verification: there is not enough extractable "
    "evidence to reach a responsible determination. Manual review is required."
)


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_verification_id() -> str:
    return f"V{_utc_now().year}-{secrets.token_hex(4).upper()}"


def _extraction_completeness(fields: dict) -> float:
    """Fraction of the 5 core identity fields present (0..1)."""
    keys = ("candidate_name", "organization", "course", "issue_date", "cert_id")
    present = sum(1 for k in keys if fields.get(k) and str(fields.get(k)).strip())
    return round(present / len(keys), 4)


def _extraction_diagnostics(extraction, completeness: float) -> dict:
    """Build the extraction diagnostics block exposed to the frontend."""
    method = extraction.extraction_method or "none"
    return {
        "method": method,
        "confidence": extraction.extraction_confidence,
        "confidence_level": (
            "high" if (extraction.extraction_confidence or 0) >= 0.7
            else "medium" if (extraction.extraction_confidence or 0) >= 0.4
            else "low"
        ),
        "text_length": extraction.extracted_text_length or len(extraction.text or ""),
        "completeness": completeness,
        "ocr_used": bool(extraction.ocr_used),
        "ocr_failed": bool(extraction.ocr_failed),
        "ocr_pages": int(extraction.ocr_pages or 0),
        "fields_detected": sum(
            1 for k in ("candidate_name", "organization", "course", "issue_date", "cert_id")
            if (extraction.fields or {}).get(k)
        ),
        "fields_total": 5,
    }


def _truncate_error(exc, max_len: int = 200) -> str:
    text = str(exc or "").strip()
    if not text:
        return "unknown error"
    return f"{text[: max_len - 1]}…" if len(text) > max_len else text


def _tampering_severity(tampering: dict) -> str:
    status = (tampering or {}).get("status")
    if status == "strong_indicators":
        return audit_service.SEVERITY_ERROR
    if status == "possible":
        return audit_service.SEVERITY_WARNING
    return audit_service.SEVERITY_SUCCESS


def _issuer_severity(iv: dict | None) -> str:
    status = (iv or {}).get("status")
    if status == "VERIFIED_BY_ISSUER":
        return audit_service.SEVERITY_SUCCESS
    if status == "NOT_VERIFIED":
        return audit_service.SEVERITY_ERROR
    if status == "ISSUER_UNKNOWN":
        return audit_service.SEVERITY_UNKNOWN
    return audit_service.SEVERITY_WARNING  # VERIFICATION_UNAVAILABLE


def _verification_code_severity(vc: dict | None) -> str:
    state = (vc or {}).get("state")
    if state == "VERIFIED_BY_ISSUER":
        return audit_service.SEVERITY_SUCCESS
    if state == "NOT_VERIFIED":
        return audit_service.SEVERITY_ERROR
    if state == "NO_CODE":
        return audit_service.SEVERITY_INFO
    return audit_service.SEVERITY_WARNING  # VERIFICATION_UNAVAILABLE


def _audit(db: Session, **kwargs) -> None:
    """Record an audit event, never letting a recording failure break the run."""
    try:
        audit_service.record_event(db, **kwargs)
    except Exception:  # noqa: BLE001 - the audit trail is best-effort by design
        db.rollback()
        logger.warning("Audit event not recorded (%s)", kwargs.get("event_type"))


def _record_evidence_events(db: Session, verification_id: str, evidence: dict) -> None:
    """Record the per-provider Phase 12 events from an executed evidence block.

    Every event is derived from the real, already-computed evidence output, so
    the trail reflects what actually happened (no fabricated stages).
    """
    forensics = evidence.get("forensics") or {}
    anomalies = evidence.get("forensic_anomalies") or []
    applicable = not bool(forensics.get("not_applicable"))
    if not applicable:
        forensics_desc = "Forensic inspection was not applicable (not a PDF)."
    elif not anomalies and not forensics.get("error"):
        forensics_desc = "Forensic inspection of the PDF structure found no anomalies."
    else:
        forensics_desc = f"Forensic inspection reported {len(anomalies)} anomaly/anomalies."
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_FORENSICS_ANALYSIS,
        stage="analysis",
        title="PDF forensics analysis",
        description=forensics_desc,
        severity=(
            audit_service.SEVERITY_WARNING
            if (anomalies or forensics.get("error"))
            else audit_service.SEVERITY_SUCCESS
        ),
        details={
            "applicable": applicable,
            "page_count": forensics.get("page_count"),
            "font_count": forensics.get("font_count"),
            "image_count": forensics.get("image_count"),
            "anomaly_count": len(anomalies),
            "error": forensics.get("error"),
        },
    )

    visual = evidence.get("visual") or {}
    visual_error = bool(visual.get("error"))
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_VISUAL_ANALYSIS,
        stage="analysis",
        title="Visual analysis",
        description=(
            "Rendered visual features analyzed."
            if not visual_error
            else "Visual analysis could not complete."
        ),
        severity=(
            audit_service.SEVERITY_WARNING if visual_error else audit_service.SEVERITY_SUCCESS
        ),
        details={
            "edge_alignment_consistency": visual.get("edge_alignment_consistency"),
            "typography_cluster_count": visual.get("typography_cluster_count"),
            "duplicated_region_count": visual.get("duplicated_region_count"),
            "blank_region_count": visual.get("blank_region_count"),
            "ink_heavy_region_count": visual.get("ink_heavy_region_count"),
            "error": visual.get("error"),
        },
    )

    tampering = evidence.get("tampering") or {}
    findings = tampering.get("findings") or []
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_TAMPERING_ANALYSIS,
        stage="analysis",
        title="Tampering assessment",
        description=(
            f"Tampering status: {tampering.get('status', 'unknown')} "
            f"({len(findings)} finding(s))."
        ),
        severity=_tampering_severity(tampering),
        details={
            "status": tampering.get("status"),
            "finding_count": len(findings),
        },
    )

    iv = evidence.get("issuer_verification") or {}
    issuer_name = iv.get("issuer") or (evidence.get("issuer") or {}).get("issuer_name")
    checked = iv.get("checked_identifiers") or []
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_ISSUER_ANALYSIS,
        stage="analysis",
        title="Issuer verification analysis",
        description=f"Issuer verification status: {iv.get('status', 'VERIFICATION_UNAVAILABLE')}.",
        severity=_issuer_severity(iv),
        details={
            "status": iv.get("status"),
            "issuer": issuer_name,
            "verification_method": iv.get("verification_method"),
            "source": iv.get("source"),
            "confidence": iv.get("confidence"),
            "checked_identifier_count": len(checked),
            "reason": iv.get("reason"),
            "error_reason": iv.get("error_reason"),
        },
    )

    vc = evidence.get("verification_codes") or {}
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_VERIFICATION_CODE_ANALYSIS,
        stage="analysis",
        title="Verification-code analysis",
        description=f"Verification-code state: {vc.get('state', 'NO_CODE')}.",
        severity=_verification_code_severity(vc),
        details={
            "state": vc.get("state"),
            "status": vc.get("status"),
            "code_count": len(vc.get("codes") or []),
            "detail": vc.get("detail"),
        },
    )

    ve = evidence.get("verification_evidence") or {}
    items = ve.get("evidence_items") or []
    by_status: dict[str, int] = {}
    for item in items:
        key = str(item.get("status") or "UNKNOWN")
        by_status[key] = by_status.get(key, 0) + 1
    assessment = ve.get("assessment")
    _audit(
        db,
        verification_id=verification_id,
        event_type=audit_service.EVENT_EVIDENCE_FUSION,
        stage="fusion",
        title="Evidence fusion",
        description=(
            f"Fused {len(items)} evidence item(s) into assessment "
            f"'{assessment or 'REQUIRES_VERIFICATION'}'."
        ),
        severity=(
            audit_service.SEVERITY_ERROR
            if assessment == "LIKELY_SUSPICIOUS"
            else audit_service.SEVERITY_WARNING
            if assessment in ("REQUIRES_VERIFICATION", "INSUFFICIENT_EVIDENCE")
            else audit_service.SEVERITY_SUCCESS
        ),
        details={
            "assessment": assessment,
            "decision": ve.get("decision"),
            "confidence": ve.get("confidence"),
            "evidence_item_count": len(items),
            "status_distribution": by_status,
            "category_status": ve.get("category_status"),
            "summary": ve.get("summary"),
        },
    )


def build_explanation(features: dict, extraction) -> list[dict]:
    """Build the flat explanation list (backward compatible).

    Combines positive trust signals and risk signals into a single list of
    {key, label, status, detail} items where 'ok' = positive, 'attention' =
    risk. This is the legacy form; the richer split is available through
    ``positive_signals`` / ``risk_signals``.
    """
    intelligence = build_intelligence(extraction, features)
    signals = build_signals(intelligence, extraction, features)
    flat = []
    for s in signals["positive"] + signals["risk"]:
        flat.append({
            "key": s["key"],
            "label": s["label"],
            "status": s["status"],
            "detail": s["detail"],
        })
    return flat


def verify_document(
    filename: str,
    content: bytes,
    db: Session,
    verification_id: str | None = None,
) -> dict:
    """Verify a document and persist the result.

    ``verification_id`` is optional: when supplied it is used as the single
    identifier for the audit trail and the persisted Verification row (the
    API generates one up front so error rows share the same id); otherwise a
    new id is generated here. The audit trail records each real step as it
    happens, so a later failure never erases what already occurred.
    """
    started = time.perf_counter()
    vid = verification_id or new_verification_id()
    logger.info("Verification request received [%s] file=%s", vid, filename or "(no name)")

    if not model_service.is_available():
        raise ModelUnavailableError()

    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_DOCUMENT_RECEIVED,
        stage="ingestion",
        title="Document received",
        description=f"Received file '{filename or '(no name)'}' for verification.",
        details={"filename": filename or "", "file_size": len(content)},
    )

    ext = validate_file(filename, content)
    stored_path = save_upload(content, ext)

    try:
        extraction = extract_document(str(stored_path), ext)
        logger.info("Verification [%s] extraction completed (%d chars)",
                    vid, len(extraction.text or ""))
        _audit(
            db,
            verification_id=vid,
            event_type=audit_service.EVENT_TEXT_EXTRACTION,
            stage="extraction",
            title="Text extraction completed",
            description=(
                f"Extracted {len(extraction.text or '')} characters via "
                f"{extraction.extraction_method or 'none'}."
            ),
            details={
                "method": extraction.extraction_method,
                "text_length": len(extraction.text or ""),
                "ocr_used": bool(extraction.ocr_used),
                "ocr_failed": bool(extraction.ocr_failed),
                "confidence": extraction.extraction_confidence,
            },
        )
    except Exception as exc:  # noqa: BLE001
        delete_upload(stored_path)
        logger.exception("Extraction failed [%s] for %s", vid, stored_path.name)
        raise ProcessingError() from exc

    features = build_features_from_extraction(extraction)
    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_FEATURE_EXTRACTION,
        stage="feature_extraction",
        title="Feature vector built",
        description=f"Built {len(features or {})} features from the extracted text.",
        details={"feature_count": len(features or {})},
    )

    try:
        result = model_service.predict(features)
    except Exception as exc:  # noqa: BLE001 - model failures are unexpected server errors (500)
        delete_upload(stored_path)
        logger.exception("Model prediction failed [%s]", vid)
        raise exc
    prediction = result["prediction"]
    risk_score = result["risk_score"]
    confidence = result["confidence"]
    model_version = result["model_version"]

    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_ML_ANALYSIS,
        stage="ml_analysis",
        title="ML model analysis completed",
        description=(
            f"Prediction={prediction} risk_score={risk_score:.3f} "
            f"confidence={confidence:.3f} model={model_version}."
        ),
        details={
            "prediction": prediction,
            "risk_score": round(risk_score, 4),
            "confidence": round(confidence, 4),
            "model_version": model_version,
        },
    )

    cert_type = {
        "academic": int(features.get("certificate_type_academic", 0)),
        "completion": int(features.get("certificate_type_completion", 0)),
        "training": int(features.get("certificate_type_training", 0)),
        "technical": int(features.get("certificate_type_technical", 0)),
    }

    # --- Phase 8 intelligence layer ---
    intelligence = build_intelligence(extraction, features)
    signals = build_signals(intelligence, extraction, features)
    review_status = compute_review_status(prediction, risk_score, signals["risk"])
    action = recommended_action(review_status)

    consistency_findings = intelligence.get("consistency_findings") or []
    high_severity_findings = sum(
        1 for f in consistency_findings
        if str(f.get("severity", "")).lower() in ("high", "critical")
    )
    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_INTELLIGENCE_ANALYSIS,
        stage="intelligence",
        title="Intelligence analysis completed",
        description=f"Review status: {review_status}.",
        details={
            "review_status": review_status,
            "structure_completeness": intelligence.get("structure_completeness"),
            "certificate_type": (intelligence.get("certificate_type") or {}).get("primary"),
            "positive_signals": len(signals["positive"]),
            "risk_signals": len(signals["risk"]),
        },
    )
    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_CONSISTENCY_ANALYSIS,
        stage="intelligence",
        title="Consistency analysis completed",
        description=f"{len(consistency_findings)} consistency finding(s).",
        severity=(
            audit_service.SEVERITY_ERROR if high_severity_findings
            else audit_service.SEVERITY_SUCCESS
        ),
        details={
            "finding_count": len(consistency_findings),
            "high_severity_count": high_severity_findings,
        },
    )

    fields = extraction.fields or {}
    certificate = Certificate(
        original_filename=filename,
        stored_filename=stored_path.name,
        file_path=str(stored_path),
        candidate_name=fields.get("candidate_name"),
        organization=fields.get("organization"),
        course=fields.get("course"),
        status=prediction,
        confidence=confidence,
        ocr_completed=extraction.ocr_used,
    )
    # db.add(certificate) + flush are intentionally deferred until just before
    # the Verification row is created, so the incremental audit commits above
    # never commit the certificate prematurely.

    # --- Phase 8 duplicate detection ---
    duplicate_info = find_duplicate(db, content, fields)

    # --- Phase 9 advisory indicators (never touch the ML prediction) ---
    ood_status = compute_ood_status(intelligence, extraction, features)
    extraction_completeness = _extraction_completeness(fields)
    extraction_diag = _extraction_diagnostics(extraction, extraction_completeness)
    review_priority = compute_review_priority(
        risk_score=risk_score,
        review_status=review_status,
        consistency_findings=intelligence["consistency_findings"],
        duplicate=duplicate_info,
        ood_status=ood_status,
        extraction_completeness=extraction_completeness,
        structure_completeness=float(intelligence.get("structure_completeness") or 0.0),
    )

    # --- Phase 12 evidence engine (M9: forensics -> visual -> tampering ->
    #     QR -> semantics -> issuer -> anomaly -> fusion). All advisory;
    #     never modifies the ML feature vector or prediction. ---
    try:
        evidence = run_phase12_pipeline(
            stored_path=stored_path,
            ext=ext,
            content=content,
            extraction=extraction,
            intelligence=intelligence,
            features=features,
            duplicate=duplicate_info,
            ml={
                "prediction": prediction,
                "risk_score": risk_score,
                "confidence": confidence,
                "model_version": model_version,
            },
            ood_status=ood_status,
        )
        _record_evidence_events(db, vid, evidence)
    except Exception as exc:  # noqa: BLE001 - forensics must never break verification
        logger.warning("Phase 12 evidence pipeline failed [%s]: %s", vid, exc)
        evidence = {
            "verification_evidence": {
                "assessment": "REQUIRES_VERIFICATION",
                "confidence": 0.4,
                "recommended_action": "manual_verification",
                "category_status": {},
                "summary": {},
                "evidence_items": [],
            },
            "forensics": {}, "forensic_anomalies": [],
            "visual": {}, "tampering": {"status": "unable_to_determine", "findings": []},
            "qr": {"status": "no_qr", "count": 0, "codes": []},
            "issuer": {"status": "unknown", "notes": ["Evidence pipeline failed."]},
            "issuer_verification": {
                "status": "VERIFICATION_UNAVAILABLE",
                "issuer": None,
                "verification_method": None,
                "verification_url": None,
                "checked_identifiers": [],
                "source": "none",
                "reason": "The evidence pipeline failed; issuer verification is unavailable.",
                "confidence": 0.0,
                "timestamp": None,
                "error_reason": "pipeline_failed",
            },
            "semantics": {}, "anomaly": {"score": 0.0, "level": "low"},
        }
        _audit(
            db,
            verification_id=vid,
            event_type=audit_service.EVENT_PIPELINE_FAILED,
            stage="analysis",
            status=audit_service.STATUS_FAILED,
            severity=audit_service.SEVERITY_WARNING,
            title="Evidence pipeline degraded",
            description=(
                "The Phase 12 evidence pipeline failed; verification continued "
                "with reduced evidence and the manual-verification assessment."
            ),
            details={"error": _truncate_error(exc)},
        )
        _audit(
            db,
            verification_id=vid,
            event_type=audit_service.EVENT_EVIDENCE_FUSION,
            stage="fusion",
            title="Evidence fusion (degraded)",
            description=(
                "Fusion produced the manual-verification assessment using reduced evidence."
            ),
            severity=audit_service.SEVERITY_WARNING,
            details={"assessment": "REQUIRES_VERIFICATION", "confidence": 0.4},
        )

    verification_evidence = evidence["verification_evidence"]

    # Decision-based message: the evidence engine's 4-state decision drives the
    # top-level message when available (additive; prediction is preserved).
    decision = verification_evidence.get("decision") or "REQUIRES_VERIFICATION"
    if decision == "SUSPICIOUS":
        message = SUSPICIOUS_MESSAGE
    elif decision == "INSUFFICIENT_EVIDENCE":
        message = INSUFFICIENT_EVIDENCE_MESSAGE
    elif decision == "VERIFIED":
        message = GENUINE_MESSAGE
    else:
        message = REQUIRES_VERIFICATION_MESSAGE

    _audit(
        db,
        verification_id=vid,
        event_type=audit_service.EVENT_FINAL_DECISION,
        stage="decision",
        title="Final decision",
        description=(
            f"Assessment {verification_evidence.get('assessment')} — decision {decision}."
        ),
        details={
            "decision": decision,
            "assessment": verification_evidence.get("assessment"),
            "decision_summary": verification_evidence.get("decision_summary", ""),
            "next_action": verification_evidence.get("next_action", "manual_verification"),
            "prediction": prediction,
            "risk_score": round(risk_score, 4),
            "confidence": round(confidence, 4),
            "model_version": model_version,
        },
    )

    db.add(certificate)
    db.flush()

    verification = Verification(
        verification_id=vid,
        certificate_id=certificate.id,
        filename=filename,
        prediction=prediction,
        label=prediction.upper(),
        risk_score=risk_score,
        confidence=confidence,
        model_version=model_version,
        extracted_info=json.dumps({k: v for k, v in fields.items() if v is not None}),
        certificate_type=json.dumps(cert_type),
        review_status=review_status,
        issuer=fields.get("organization"),
        issue_date=fields.get("issue_date"),
        file_fingerprint=file_fingerprint(content),
        cert_id_fingerprint=cert_id_fingerprint(fields.get("cert_id")),
        identity_fingerprint=identity_fingerprint(fields),
        duplicate_of=duplicate_info["duplicate_of"],
        duplicate_type=duplicate_info["duplicate_type"],
        ood_status=ood_status,
        review_priority=review_priority,
        intelligence_json=json.dumps({
            "intelligence": intelligence,
            "positive_signals": signals["positive"],
            "risk_signals": signals["risk"],
            "duplicate": duplicate_info,
            "ood_status": ood_status,
            "review_priority": review_priority,
            "extraction": extraction_diag,
            "features": features,
        }),
        # --- Phase 10 extraction diagnostics ---
        extraction_metadata=json.dumps(extraction_diag),
        # --- Phase 12 evidence engine ---
        evidence_json=json.dumps({
            "verification_evidence": verification_evidence,
            "forensics": evidence["forensics"],
            "forensic_anomalies": evidence["forensic_anomalies"],
            "visual": evidence["visual"],
            "tampering": evidence["tampering"],
            "qr": evidence["qr"],
            "issuer": evidence["issuer"],
            "issuer_verification": evidence.get("issuer_verification"),
            "verification_codes": evidence["verification_codes"],
            "semantics": evidence["semantics"],
            "anomaly": evidence["anomaly"],
        }),
    )
    db.add(verification)
    db.commit()

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.info(
        "Verification [%s] %s: prediction=%s risk=%.3f conf=%.3f model=%s "
        "review=%s duplicate=%s ood=%s priority=%s duration_ms=%.1f file=%s",
        vid, verification.verification_id, prediction, risk_score,
        confidence, model_version, review_status,
        duplicate_info["duplicate_type"] or "none", ood_status, review_priority,
        elapsed_ms, filename,
    )

    return {
        "verification_id": verification.verification_id,
        "prediction": prediction,
        "label": prediction.upper(),
        "risk_score": risk_score,
        "confidence": confidence,
        "message": message,
        "model_version": model_version,
        "certificate_type": cert_type,
        "explanation": build_explanation(features, extraction),
        "extracted": {k: v for k, v in fields.items() if v is not None},
        "warnings": extraction.warnings,
        "created_at": verification.created_at,
        "review_status": review_status,
        "recommended_action": action,
        "intelligence": intelligence,
        "positive_signals": signals["positive"],
        "risk_signals": signals["risk"],
        "duplicate": duplicate_info,
        # --- Phase 9 advisory indicators ---
        "ood_status": ood_status,
        "review_priority": review_priority,
        "extraction_completeness": extraction_completeness,
        # --- Phase 10 extraction diagnostics ---
        "extraction": extraction_diag,
        # --- Phase 12 evidence engine (additive) ---
        "verification_evidence": verification_evidence,
        # --- upgrade: issuer verification (advisory, additive) ---
        "issuer_verification": evidence.get("issuer_verification") or {},
        # --- upgrade: decision surfaced at the top level (additive) ---
        "decision": decision,
        "decision_summary": verification_evidence.get("decision_summary", ""),
        "next_action": verification_evidence.get("next_action", "manual_verification"),
    }