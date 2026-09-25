"""Human-review feedback model (Phase 9A).

Stores a single reviewer decision per verification. Feedback NEVER modifies the
production model, threshold, or feature schema: it is evidence collected for
error analysis and, later, for a candidate training dataset.

Reviewer labels:
  - confirmed_genuine    the reviewer verified the certificate as genuine
  - confirmed_suspicious the reviewer verified the certificate as suspicious
  - uncertain            the reviewer could not decide
  - not_reviewed         no reviewer decision yet (default; not stored)

Dataset-split metadata is stored on the same row so a candidate dataset built
from confirmed feedback can preserve train/test separation and prevent leakage.
"""

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, UniqueConstraint

from app.database.base import Base
from app.models.certificate import utc_now

# Reviewer label vocabulary. These constants are shared by the API, schemas,
# offline analysis tooling, and tests.
REVIEWER_LABELS = ("confirmed_genuine", "confirmed_suspicious", "uncertain")
QUALIFYING_LABELS = ("confirmed_genuine", "confirmed_suspicious")
SPLIT_LABELS = ("train", "test")


class VerificationFeedback(Base):
    __tablename__ = "verification_feedback"
    __table_args__ = (
        # One reviewer decision per verification: duplicate submissions are
        # rejected at the database level as well as in the API layer.
        UniqueConstraint("verification_id", name="uq_verification_feedback_verification_id"),
    )

    id = Column(Integer, primary_key=True)
    verification_id = Column(
        String, index=True, nullable=False
    )
    # Clerk user id that owns the verification this feedback refers to. Used to
    # scope feedback queries to a user and to enforce ownership at the API
    # layer. Null only ever appears for rows created by buggy pre-auth code.
    user_id = Column(String, index=True, nullable=True)
    reviewer_label = Column(String, nullable=False, index=True)
    reviewer_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, default=utc_now, index=True)

    # --- Snapshot of the original AI result (immutable evidence) ---
    original_prediction = Column(String, nullable=False)
    original_risk_score = Column(Float, nullable=False)
    original_confidence = Column(Float, nullable=True)
    model_version = Column(String, nullable=True)
    certificate_type = Column(String, nullable=True, index=True)
    extraction_completeness = Column(Float, nullable=True)
    review_status = Column(String, nullable=True)
    issuer = Column(String, nullable=True, index=True)
    ood_status = Column(String, nullable=True)
    review_priority = Column(String, nullable=True)

    # --- Phase 12 evidence-engine snapshot (immutable evidence) ---
    final_assessment = Column(String, nullable=True)  # LIKELY_GENUINE | ...
    anomaly_score = Column(Float, nullable=True)
    anomaly_level = Column(String, nullable=True)

    # --- Duplicate / reuse fingerprints (for leakage protection) ---
    file_fingerprint = Column(String, nullable=True, index=True)
    cert_id_fingerprint = Column(String, nullable=True, index=True)
    identity_fingerprint = Column(String, nullable=True)

    # --- Dataset-split metadata (set by the candidate dataset builder) ---
    split = Column(String, nullable=True, index=True)  # "train" | "test"
    dataset_batch = Column(String, nullable=True, index=True)

    # Reviewer/model disagreement is computed at write time and stored so the
    # analytics can report it without re-deriving the semantics.
    is_disagreement = Column(Boolean, nullable=True)

    created_at = Column(DateTime, default=utc_now)