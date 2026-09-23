"""Audit trail service.

Records append-only, chronological events describing what the verification
system actually did for a given verification_id. Each event corresponds to a
real backend operation; no timestamps or stages are invented. Events are
written immediately (each in its own commit) so that a later failure cannot
erase what actually happened, and they are never updated or deleted.

Security contract:
  * sensitive identifiers / verification codes are masked before storage;
  * no secrets, environment values, or raw document contents are stored;
  * error messages are truncated to a safe length.
"""

import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.audit import AuditEvent
from app.services.issuer.verifier import mask_identifier

logger = get_logger("audit_service")

# ---------------------------------------------------------------------------
# Event type vocabulary
# ---------------------------------------------------------------------------
EVENT_DOCUMENT_RECEIVED = "DOCUMENT_RECEIVED"
EVENT_TEXT_EXTRACTION = "TEXT_EXTRACTION"
EVENT_FEATURE_EXTRACTION = "FEATURE_EXTRACTION"
EVENT_ML_ANALYSIS = "ML_ANALYSIS"
EVENT_INTELLIGENCE_ANALYSIS = "INTELLIGENCE_ANALYSIS"
EVENT_CONSISTENCY_ANALYSIS = "CONSISTENCY_ANALYSIS"
EVENT_FORENSICS_ANALYSIS = "FORENSICS_ANALYSIS"
EVENT_VISUAL_ANALYSIS = "VISUAL_ANALYSIS"
EVENT_TAMPERING_ANALYSIS = "TAMPERING_ANALYSIS"
EVENT_ISSUER_ANALYSIS = "ISSUER_ANALYSIS"
EVENT_VERIFICATION_CODE_ANALYSIS = "VERIFICATION_CODE_ANALYSIS"
EVENT_EVIDENCE_FUSION = "EVIDENCE_FUSION"
EVENT_FINAL_DECISION = "FINAL_DECISION"
EVENT_REVIEW_ACTION = "REVIEW_ACTION"
EVENT_PIPELINE_FAILED = "PIPELINE_FAILED"

# ---------------------------------------------------------------------------
# Outcome status vocabulary
# ---------------------------------------------------------------------------
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_RECORDED = "recorded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Display severity vocabulary (mapped to frontend colors; never red for
# "unavailable / unknown / insufficient evidence" outcomes).
# ---------------------------------------------------------------------------
SEVERITY_SUCCESS = "success"
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
SEVERITY_UNKNOWN = "unknown"

# Keys whose values are masked before storage (defensive backstop; callers
# should pass already-masked identifiers).
_SENSITIVE_KEYS = frozenset({
    "code", "identifier", "token", "verification_code",
    "cert_id", "credential_id", "verification_codes",
    "checked_identifier", "checked_identifiers",
})

_MAX_DESCRIPTION = 500


def _derive_severity(status: str) -> str:
    """Map an outcome status to the display severity."""
    return {
        STATUS_COMPLETED: SEVERITY_SUCCESS,
        STATUS_FAILED: SEVERITY_ERROR,
        STATUS_RECORDED: SEVERITY_INFO,
        STATUS_UNAVAILABLE: SEVERITY_WARNING,
        STATUS_SKIPPED: SEVERITY_UNKNOWN,
    }.get(status, SEVERITY_INFO)


def _mask_value(value):
    """Mask a sensitive scalar (used for the defensive sensitive-key backstop)."""
    if value is None:
        return None
    return mask_identifier(str(value))


def _sanitize_details(value):
    """Recursively mask values under sensitive keys; leave everything else intact."""
    if isinstance(value, dict):
        return {
            k: (_mask_value(v) if k in _SENSITIVE_KEYS else _sanitize_details(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_details(v) for v in value]
    return value


def _safe_text(value, max_len: int = _MAX_DESCRIPTION) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        text = f"{text[: max_len - 1]}…"
    return text


def record_event(
    db: Session,
    *,
    verification_id: str,
    event_type: str,
    title: str,
    status: str = STATUS_COMPLETED,
    severity: str | None = None,
    description: str | None = None,
    details: dict | None = None,
    stage: str | None = None,
) -> AuditEvent:
    """Append one audit event and commit it immediately.

    The commit is intentional: the event survives even if the rest of the
    verification later fails, so the trail reflects what actually happened.
    """
    if severity is None:
        severity = _derive_severity(status)
    event = AuditEvent(
        verification_id=verification_id,
        event_type=event_type,
        stage=stage,
        status=status,
        severity=severity,
        title=_safe_text(title, 200) or event_type,
        description=_safe_text(description),
        details=json.dumps(_sanitize_details(details or {}), default=str),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_audit_events(db: Session, verification_id: str) -> list[AuditEvent]:
    """Return the append-only timeline for a verification (oldest first)."""
    return (
        db.query(AuditEvent)
        .filter(AuditEvent.verification_id == verification_id)
        .order_by(AuditEvent.id.asc())
        .all()
    )


def event_count(db: Session, verification_id: str) -> int:
    """Number of recorded events for a verification (used for failure checks)."""
    return db.query(AuditEvent).filter(
        AuditEvent.verification_id == verification_id
    ).count()


def _parse_details(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def serialize_event(event: AuditEvent) -> dict:
    """Convert an AuditEvent into the API payload shape."""
    return {
        "id": event.id,
        "verification_id": event.verification_id,
        "event_type": event.event_type,
        "stage": event.stage,
        "status": event.status,
        "severity": event.severity,
        "title": event.title,
        "description": event.description,
        "details": _parse_details(event.details),
        "created_at": event.created_at,
    }