"""Phase 12 evidence pipeline (M9).

Runs every Phase 12 provider (PDF forensics, visual analysis, tampering,
QR, semantics, issuer intelligence, anomaly scoring) and fuses the result into
the final assessment. Called from ``verification_service.verify_document``.

The ML feature vector and the ML prediction are strictly read-only inputs here;
nothing in this module can change them.
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger
from app.core.config import settings
from app.services.anomaly_service import compute_anomaly
from app.services.evidence_fusion import build_evidence, fuse
from app.services.extraction_service import ExtractionResult
from app.services.issuer import issuer_verification
from app.services.pdf_forensics import ForensicReport, analyze_pdf
from app.services.qr_service import QRReport, analyze_qr
from app.services.semantic_service import extract_semantics
from app.services.tampering_service import assess_tampering
from app.services.verification_code_service import VerificationCodeReport, analyze_verification_codes
from app.services.visual_analysis import VisualReport, analyze_visual

logger = get_logger("phase12_pipeline")

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # type: ignore


def _render_first_page(path: str, ext: str):
    """Render the first page of a PDF, or return the image itself."""
    try:
        if ext == "pdf":
            if fitz is None:
                return None
            doc = fitz.open(path)
            try:
                page = doc[0]
                pix = page.get_pixmap(dpi=150)
                from PIL import Image
                return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            finally:
                doc.close()
        else:
            from PIL import Image
            img = Image.open(path)
            img.load()
            return img.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - rendering must fail gracefully
        logger.warning("First-page render failed: %s", exc)
        return None


def _empty_forensic() -> ForensicReport:
    report = ForensicReport()
    report.signals["not_applicable"] = True
    report.signals["error"] = "not a PDF"
    return report


def run_phase12_pipeline(*, stored_path: Path, ext: str, content: bytes,
                         extraction: ExtractionResult, intelligence: dict,
                         features: dict, duplicate: dict, ml: dict,
                         ood_status: str = "normal") -> dict:
    """Run all Phase 12 providers and return the fused evidence block."""
    # ---- M1: PDF forensics ----
    forensic = analyze_pdf(str(stored_path), raw=content) if ext == "pdf" else _empty_forensic()

    # ---- M2 + M3: visual, QR ----
    image = _render_first_page(str(stored_path), ext)
    visual: VisualReport = VisualReport()
    if image is not None:
        visual = analyze_visual(image)
    qr: QRReport = analyze_qr(image) if image is not None else QRReport()

    # ---- M2: tampering (advisory) ----
    tampering = assess_tampering(forensic, visual, metadata={
        "method": extraction.extraction_method,
        "ocr_used": extraction.ocr_used,
    })

    # ---- M5: semantics ----
    semantic = extract_semantics(extraction.text or "")

    # ---- M4: issuer intelligence ----
    fields = extraction.fields or {}
    verification_codes_extracted = list(fields.get("verification_codes") or [])
    issuer = issuer_verification.assess(
        issuer_name=fields.get("organization"),
        qr_report=qr,
        verification_codes=verification_codes_extracted,
        certificate_data=fields,
    )

    # ---- M6: anomaly scoring ----
    anomaly = compute_anomaly(extraction, intelligence, features,
                              forensic=forensic, visual=visual,
                              tampering=tampering, issuer=issuer)

    # ---- Upgrade: verification-code analysis ----
    verification_codes: VerificationCodeReport = analyze_verification_codes(
        extraction,
        external_verify_enabled=settings.external_verify_enabled,
        issuer_verification=issuer.issuer_verification,
    )

    # ---- M7: evidence fusion ----
    items = build_evidence(
        ml=ml,
        extraction=extraction,
        intelligence=intelligence,
        semantic=semantic,
        forensic=forensic,
        visual=visual,
        tampering=tampering,
        qr=qr,
        issuer=issuer,
        anomaly=anomaly,
        duplicate=duplicate,
        verification_codes=verification_codes,
        features=features,
    )
    fusion = fuse(
        items,
        ml=ml,
        extraction=extraction,
        tampering=tampering,
        qr=qr,
        issuer=issuer,
        anomaly=anomaly,
        ood_status=ood_status,
        duplicate=duplicate,
        verification_codes=verification_codes,
    )
    fusion["evidence_items"] = items

    return {
        "verification_evidence": fusion,
        "forensics": forensic.signals,
        "forensic_anomalies": forensic.anomalies,
        "visual": visual.signals,
        "tampering": {
            "status": tampering.status,
            "findings": tampering.findings,
            "signals": tampering.signals,
        },
        "qr": {
            "status": qr.status,
            "count": qr.count,
            "codes": [c.payload for c in qr.codes],
            "invalid_qr": qr.invalid_qr,
            "notes": qr.notes,
        },
        "issuer": {
            "status": issuer.status,
            "issuer_name": issuer.issuer_name,
            "issuer_identified": issuer.issuer_identified,
            "issuer_state": issuer.issuer_state,
            "verification_result": issuer.verification_result,
            "verification_methods": issuer.verification_methods,
            "verification_detail": issuer.verification_detail,
            "domain_consistency": issuer.domain_consistency,
            "qr_domains": issuer.qr_domains,
            "candidate_domains": issuer.candidate_domains,
            "external": issuer.external,
            "notes": issuer.notes,
        },
        "issuer_verification": (
            issuer.issuer_verification.as_dict()
            if issuer.issuer_verification is not None
            else None
        ),
        "verification_codes": {
            "status": verification_codes.status,
            "state": verification_codes.state,
            "codes": verification_codes.codes,
            "detail": verification_codes.detail,
            "notes": verification_codes.notes,
        },
        "semantics": {
            "credential_statement_present": semantic.credential_statement_present,
            "roles": semantic.roles,
            "credential_level": semantic.credential_level,
            "verification_present": semantic.verification_present,
        },
        "anomaly": {
            "score": anomaly.score,
            "level": anomaly.level,
            "contributors": anomaly.contributors,
        },
    }