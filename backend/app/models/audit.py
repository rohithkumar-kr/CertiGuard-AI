"""Verification audit trail model.

Stores a chronological, append-only record of what the verification system
actually did for a given verification_id: from document receipt through text
extraction, feature extraction, ML analysis, intelligence/consistency,
forensics/visual/tampering, issuer analysis, evidence fusion, the final
decision, and any later human review action.

Contract:
  * rows are never updated or deleted;
  * every event corresponds to a real backend operation (no fabricated
    timestamps or stages);
  * created_at is UTC (naive, consistent with the rest of the schema);
  * sensitive identifiers/codes are masked before they are written;
  * the ``details`` column stores a small JSON payload (never secrets).
"""

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database.base import Base
from app.models.certificate import utc_now


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    verification_id = Column(String, index=True, nullable=False)
    # Clerk user id that owns the verification these audit events belong to.
    # Scopes audit queries to a user; null only for legacy rows.
    user_id = Column(String, index=True, nullable=True)
    # Stable event-type code (e.g. "ML_ANALYSIS"); see audit_service.EVENT_*.
    event_type = Column(String, index=True, nullable=False)
    # Coarse processing phase for grouping (ingestion / extraction / analysis /
    # fusion / decision / review / failure).
    stage = Column(String, nullable=True)
    # Outcome status: completed | failed | recorded | unavailable | skipped.
    status = Column(String, nullable=False)
    # Display severity: success | info | warning | error | unknown.
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # Small JSON payload describing the event (codes/identifiers masked).
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, index=True)