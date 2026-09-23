"""API routes for the certificate verification system.

Endpoints:
  GET  /api/health
  GET  /api/model/info
  POST /api/verify
  GET  /api/verifications
  GET  /api/verifications/summary
  GET  /api/metrics
"""

import json
import threading
import time
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ModelUnavailableError
from app.core.logging import get_logger
from app.database.database import get_db
from app.ml import model as model_service
from app.models.feedback import VerificationFeedback
from app.models.verification import Verification
from app.schemas.feedback import (
    FeedbackAnalyticsResponse,
    FeedbackCreate,
    FeedbackResponse,
    FeedbackSummaryResponse,
)
from app.schemas.verification import (
    AuditEvent,
    AuditTrailResponse,
    HealthResponse,
    MetricsResponse,
    ModelInfoResponse,
    VerificationDetailResponse,
    VerificationRecord,
    VerificationResponse,
    VerificationSummary,
)
from app.services import audit_service
from app.services.feedback_service import feedback_analytics, feedback_summary, record_feedback
from app.services.verification_service import new_verification_id, verify_document

logger = get_logger("api")
router = APIRouter()

# Bound concurrent verifications so a burst of uploads cannot exhaust workers.
_verify_slots = threading.BoundedSemaphore(
    max(1, settings.max_concurrent_verifications)
)


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        model_version=model_service.model_version(),
        model_loaded=model_service.is_available(),
    )


@router.get("/model/info", response_model=ModelInfoResponse)
def model_info():
    info = model_service.model_info()
    return ModelInfoResponse(**info)


@router.post("/verify", response_model=VerificationResponse)
async def verify(files: list[UploadFile] = File(..., alias="file"), db: Session = Depends(get_db)):
    if len(files) != 1:
        raise AppError(message="Exactly one file must be uploaded.")
    file = files[0]
    if not _verify_slots.acquire(blocking=False):
        logger.warning("Verification concurrency limit reached (%d)", settings.max_concurrent_verifications)
        raise AppError(message="Too many verifications in progress. Please try again shortly.")
    started = time.perf_counter()
    vid: str | None = None
    try:
        content = await file.read()
        logger.info("Received file=%s size=%d", file.filename or "(no name)", len(content))
        vid = new_verification_id()
        result = verify_document(file.filename or "", content, db, verification_id=vid)
        logger.info("Verification ok in %.1f ms", (time.perf_counter() - started) * 1000)
        return VerificationResponse(**result)
    except AppError as exc:
        db.rollback()
        record_error(db, file.filename, exc, verification_id=vid)
        raise
    except Exception as exc:  # noqa: BLE001 - unexpected errors surface as 500, never tracebacks
        db.rollback()
        logger.exception("Unhandled error during verification for %s", file.filename)
        raise exc
    finally:
        _verify_slots.release()


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@router.get("/verifications", response_model=list[VerificationRecord])
def list_verifications(
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=200),
    prediction: str = Query("", max_length=20),
    certificate_type: str = Query("", max_length=20),
    sort: str = Query("newest", pattern="^(newest|oldest)$"),
    review_status: str = Query("", max_length=20),
    issuer: str = Query("", max_length=200),
    date_from: str = Query("", max_length=10),
    date_to: str = Query("", max_length=10),
    risk_min: float = Query(None, ge=0.0, le=1.0),
    risk_max: float = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    query = db.query(Verification)
    if prediction:
        query = query.filter(Verification.prediction == prediction)
    if review_status:
        query = query.filter(Verification.review_status == review_status)
    if issuer:
        like = f"%{issuer.strip()}%"
        query = query.filter(Verification.issuer.ilike(like))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(Verification.filename.ilike(like))
    if risk_min is not None:
        query = query.filter(Verification.risk_score >= risk_min)
    if risk_max is not None:
        query = query.filter(Verification.risk_score <= risk_max)
    from_d = _parse_date(date_from)
    to_d = _parse_date(date_to)
    if from_d is not None:
        query = query.filter(Verification.created_at >= datetime(from_d.year, from_d.month, from_d.day))
    if to_d is not None:
        query = query.filter(
            Verification.created_at < datetime(to_d.year, to_d.month, to_d.day + 1)
        )
    rows = query.all()

    if certificate_type:
        rows = [r for r in rows if _record_has_cert_type(r, certificate_type)]

    rows.sort(key=lambda r: (r.created_at or r.id), reverse=(sort == "newest"))
    feedback = _feedback_map(db)
    return [_enrich_record(r, feedback.get(r.verification_id)) for r in rows[:limit]]


@router.get("/verifications/summary", response_model=VerificationSummary)
def verifications_summary(
    search: str = Query("", max_length=200),
    prediction: str = Query("", max_length=20),
    certificate_type: str = Query("", max_length=20),
    review_status: str = Query("", max_length=20),
    issuer: str = Query("", max_length=200),
    date_from: str = Query("", max_length=10),
    date_to: str = Query("", max_length=10),
    risk_min: float = Query(None, ge=0.0, le=1.0),
    risk_max: float = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    query = db.query(Verification)
    if prediction:
        query = query.filter(Verification.prediction == prediction)
    if review_status:
        query = query.filter(Verification.review_status == review_status)
    if issuer:
        like = f"%{issuer.strip()}%"
        query = query.filter(Verification.issuer.ilike(like))
    if search:
        like = f"%{search.strip()}%"
        query = query.filter(Verification.filename.ilike(like))
    if risk_min is not None:
        query = query.filter(Verification.risk_score >= risk_min)
    if risk_max is not None:
        query = query.filter(Verification.risk_score <= risk_max)
    from_d = _parse_date(date_from)
    to_d = _parse_date(date_to)
    if from_d is not None:
        query = query.filter(Verification.created_at >= datetime(from_d.year, from_d.month, from_d.day))
    if to_d is not None:
        query = query.filter(
            Verification.created_at < datetime(to_d.year, to_d.month, to_d.day + 1)
        )
    rows = query.all()
    if certificate_type:
        rows = [r for r in rows if _record_has_cert_type(r, certificate_type)]

    successful = [r for r in rows if r.prediction != "error"]
    avg_risk = (round(sum(r.risk_score for r in successful) / len(successful), 4)
                if successful else 0.0)
    return VerificationSummary(
        total=len(rows),
        genuine_count=sum(1 for r in successful if r.prediction == "genuine"),
        suspicious_count=sum(1 for r in successful if r.prediction == "suspicious"),
        manual_review_count=sum(1 for r in successful if r.review_status == "manual_review"),
        average_risk_score=avg_risk,
    )


def _record_has_cert_type(record: Verification, cert_type: str) -> bool:
    """True if a verification record's persisted cert-type flags include the type."""
    raw = record.certificate_type or ""
    try:
        flags = json.loads(raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(flags, dict):
        return False
    return bool(flags.get(cert_type))


def _feedback_map(db: Session) -> dict[str, VerificationFeedback]:
    """Map verification_id -> feedback for all feedback rows in one query."""
    rows = db.query(VerificationFeedback).all()
    return {r.verification_id: r for r in rows}


def _enrich_record(record: Verification, feedback: VerificationFeedback | None) -> dict:
    """Extend a persisted Verification into a VerificationRecord dict, adding
    the Phase 9 advisory indicators and the reviewer decision."""
    data = {
        "verification_id": record.verification_id,
        "filename": record.filename,
        "prediction": record.prediction,
        "risk_score": record.risk_score,
        "confidence": record.confidence,
        "model_version": record.model_version,
        "created_at": record.created_at,
        "review_status": record.review_status,
        "issuer": record.issuer,
        "certificate_type": record.certificate_type,
        "duplicate_of": record.duplicate_of,
        "duplicate_type": record.duplicate_type,
        "ood_status": record.ood_status,
        "review_priority": record.review_priority,
    }
    if feedback is not None:
        data["reviewer_label"] = feedback.reviewer_label
        data["reviewed_at"] = feedback.reviewed_at
        data["is_disagreement"] = feedback.is_disagreement
    return data


def _parse_certificate_type(raw: str | None) -> dict:
    """Parse the persisted certificate-type flags; missing/old rows default to {}."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _extraction_completeness(record: Verification) -> float:
    """Compute extraction completeness (0..1) from the persisted extracted_info."""
    if not record.extracted_info:
        return 0.0
    try:
        fields = json.loads(record.extracted_info)
    except (ValueError, TypeError):
        return 0.0
    if not isinstance(fields, dict):
        return 0.0
    keys = ("candidate_name", "organization", "course", "issue_date", "cert_id")
    present = sum(1 for k in keys if fields.get(k))
    return round(present / len(keys), 4)


@router.get("/metrics", response_model=MetricsResponse)
def metrics(db: Session = Depends(get_db)):
    rows = db.query(Verification).all()
    successful = [r for r in rows if r.prediction != "error"]
    prediction_distribution = dict(Counter(r.prediction for r in successful))
    model_versions = dict(Counter(r.model_version for r in rows))

    cert_type_counter: Counter = Counter()
    for r in successful:
        flags = _parse_certificate_type(r.certificate_type)
        for flag_name, flag_value in flags.items():
            if flag_value:
                cert_type_counter[flag_name] += 1
    certificate_type_distribution = dict(cert_type_counter)

    review_status_counter: Counter = Counter(
        r.review_status or "low_risk" for r in successful
    )
    issuer_counter: Counter = Counter()
    for r in successful:
        if r.issuer:
            issuer_counter[r.issuer] += 1

    def avg(values):
        return round(sum(values) / len(values), 4) if values else 0.0

    recent = sorted(rows, key=lambda r: (r.created_at or r.id), reverse=True)[:10]
    manual_review_count = review_status_counter.get("manual_review", 0)
    manual_review_rate = round(manual_review_count / len(successful), 4) if successful else 0.0
    return MetricsResponse(
        total_verifications=len(rows),
        genuine_count=sum(1 for r in successful if r.prediction == "genuine"),
        suspicious_count=sum(1 for r in successful if r.prediction == "suspicious"),
        error_count=sum(1 for r in rows if r.prediction == "error"),
        prediction_distribution=prediction_distribution,
        certificate_type_distribution=certificate_type_distribution,
        average_risk_score=avg([r.risk_score for r in successful]),
        average_confidence=avg([r.confidence for r in successful]),
        model_versions=model_versions,
        recent=[VerificationRecord.model_validate(r) for r in recent],
        review_status_distribution=dict(review_status_counter),
        average_extraction_completeness=avg([_extraction_completeness(r) for r in successful]),
        issuer_distribution=dict(issuer_counter.most_common(15)),
        manual_review_rate=manual_review_rate,
    )


def record_error(db: Session, filename: str | None, exc: AppError,
                 verification_id: str | None = None) -> None:
    """Persist a failed verification so monitoring shows errors.

    ``verification_id`` is the id that the verification attempt was started
    with (if any); the failure audit event shares that id so the timeline stays
    coherent. Pre-pipeline failures (no id yet) fall back to the V-ERR- form.
    """
    try:
        vid = verification_id or f"V-ERR-{abs(hash((filename, exc.message))) % 10**6}"
        verification = Verification(
            verification_id=vid,
            filename=filename,
            prediction="error",
            label="ERROR",
            risk_score=0.0,
            confidence=0.0,
            model_version=model_service.model_version(),
            error=exc.message,
        )
        db.add(verification)
        db.commit()
        _record_failure_event(db, vid, exc)
    except Exception:  # noqa: BLE001 - never let error logging break the response
        db.rollback()
        logger.exception("Could not record failed verification")


def _record_failure_event(db: Session, vid: str, exc: AppError) -> None:
    """Append the failure event for a failed verification (best-effort)."""
    try:
        started = audit_service.event_count(db, vid) > 0
        audit_service.record_event(
            db,
            verification_id=vid,
            event_type=audit_service.EVENT_PIPELINE_FAILED,
            stage="failure",
            status=audit_service.STATUS_FAILED,
            severity=audit_service.SEVERITY_ERROR,
            title="Verification failed",
            description=(
                "The verification pipeline failed before producing a result."
                if not started
                else "The verification pipeline failed during processing."
            ),
            details={
                "phase": "pre_processing" if not started else "processing",
                "error": exc.message,
            },
        )
    except Exception:  # noqa: BLE001 - audit must never break error recording
        db.rollback()
        logger.exception("Could not record failure audit event")


# ---------------------------------------------------------------------------
# Phase 9: reviewer feedback + analytics
# ---------------------------------------------------------------------------

def _parse_intelligence_json(record: Verification) -> dict:
    """Parse the persisted intelligence snapshot (best-effort)."""
    raw = record.intelligence_json
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _parse_extraction_metadata(record: Verification) -> dict:
    """Parse the persisted extraction diagnostics (best-effort)."""
    raw = record.extraction_metadata
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _parse_evidence_json(record: Verification) -> dict:
    """Parse the persisted Phase 12 evidence snapshot (best-effort)."""
    raw = record.evidence_json
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


@router.get("/verifications/{verification_id}", response_model=VerificationDetailResponse)
def verification_detail(verification_id: str, db: Session = Depends(get_db)):
    """Full detail for a single verification (reviewer workflow, 9H)."""
    record = (
        db.query(Verification)
        .filter(Verification.verification_id == verification_id)
        .first()
    )
    if record is None:
        raise AppError("Verification not found.")

    feedback = (
        db.query(VerificationFeedback)
        .filter(VerificationFeedback.verification_id == verification_id)
        .first()
    )
    snapshot = _parse_intelligence_json(record)
    evidence_snapshot = _parse_evidence_json(record)
    detail = {
        "verification_id": record.verification_id,
        "filename": record.filename,
        "prediction": record.prediction,
        "label": record.label,
        "risk_score": record.risk_score,
        "confidence": record.confidence,
        "model_version": record.model_version,
        "created_at": record.created_at,
        "error": record.error,
        "review_status": record.review_status,
        "issuer": record.issuer,
        "certificate_type": record.certificate_type,
        "extracted_info": record.extracted_info,
        "duplicate_of": record.duplicate_of,
        "duplicate_type": record.duplicate_type,
        "ood_status": record.ood_status or snapshot.get("ood_status"),
        "review_priority": record.review_priority or snapshot.get("review_priority"),
        "extraction": _parse_extraction_metadata(record) or snapshot.get("extraction") or {},
        "intelligence": snapshot.get("intelligence") or {},
        "positive_signals": snapshot.get("positive_signals") or [],
        "risk_signals": snapshot.get("risk_signals") or [],
        "duplicate": snapshot.get("duplicate") or {
            "is_duplicate": record.duplicate_of is not None,
            "duplicate_of": record.duplicate_of,
            "duplicate_type": record.duplicate_type,
        },
        # --- Phase 12 evidence engine ---
        "verification_evidence": evidence_snapshot.get("verification_evidence") or {},
        "issuer_verification": evidence_snapshot.get("issuer_verification") or {},
        "evidence_details": {
            "forensics": evidence_snapshot.get("forensics") or {},
            "forensic_anomalies": evidence_snapshot.get("forensic_anomalies") or [],
            "visual": evidence_snapshot.get("visual") or {},
            "tampering": evidence_snapshot.get("tampering") or {},
            "qr": evidence_snapshot.get("qr") or {},
            "issuer": evidence_snapshot.get("issuer") or {},
            "issuer_verification": evidence_snapshot.get("issuer_verification") or {},
            "verification_codes": evidence_snapshot.get("verification_codes") or {},
            "semantics": evidence_snapshot.get("semantics") or {},
            "anomaly": evidence_snapshot.get("anomaly") or {},
        },
    }
    if feedback is not None:
        detail["reviewer_label"] = feedback.reviewer_label
        detail["reviewer_note"] = feedback.reviewer_note
        detail["reviewed_at"] = feedback.reviewed_at
        detail["is_disagreement"] = feedback.is_disagreement
    return VerificationDetailResponse(**detail)


@router.get("/verifications/{verification_id}/audit", response_model=AuditTrailResponse)
def verification_audit(verification_id: str, db: Session = Depends(get_db)):
    """Append-only audit trail / investigation timeline for a verification.

    Returns the chronological events (oldest first). An empty list is a valid
    result for a verification that predates audit recording.
    """
    record = (
        db.query(Verification)
        .filter(Verification.verification_id == verification_id)
        .first()
    )
    if record is None:
        raise AppError("Verification not found.")
    events = audit_service.list_audit_events(db, verification_id)
    return AuditTrailResponse(
        verification_id=verification_id,
        events=[AuditEvent(**audit_service.serialize_event(e)) for e in events],
    )


@router.post("/verifications/{verification_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(
    verification_id: str,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
):
    """Record a human-review decision for a verification (9B).

    Human feedback NEVER modifies the ML model, the prediction, or the risk
    score. One decision per verification; duplicate submissions are rejected.
    """
    feedback = record_feedback(
        db, verification_id, payload.reviewer_label, payload.reviewer_note
    )
    return FeedbackResponse.model_validate(feedback)


@router.get("/feedback/summary", response_model=FeedbackSummaryResponse)
def feedback_summary_endpoint(db: Session = Depends(get_db)):
    """Summary counts over the reviewer feedback collection (9B)."""
    return FeedbackSummaryResponse(**feedback_summary(db))


@router.get("/feedback/analytics", response_model=FeedbackAnalyticsResponse)
def feedback_analytics_endpoint(db: Session = Depends(get_db)):
    """Monitoring view over reviewed certificates (9I)."""
    return FeedbackAnalyticsResponse(**feedback_analytics(db))