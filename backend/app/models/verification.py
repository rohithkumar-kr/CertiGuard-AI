from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship

from app.database.base import Base
from app.models.certificate import utc_now


class Verification(Base):
    __tablename__ = "verifications"
    id = Column(Integer, primary_key=True)
    verification_id = Column(String, unique=True, index=True, nullable=False)
    certificate_id = Column(Integer, ForeignKey("certificates.id"), nullable=True)
    filename = Column(String, nullable=True)
    prediction = Column(String, nullable=False)
    label = Column(String, nullable=True)
    risk_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    error = Column(String, nullable=True)
    extracted_info = Column(Text, nullable=True)
    certificate_type = Column(Text, nullable=True)
    review_status = Column(String, nullable=True)
    issuer = Column(String, nullable=True)
    issue_date = Column(String, nullable=True)
    file_fingerprint = Column(String, nullable=True, index=True)
    cert_id_fingerprint = Column(String, nullable=True, index=True)
    identity_fingerprint = Column(String, nullable=True)
    duplicate_of = Column(String, nullable=True)
    duplicate_type = Column(String, nullable=True)
    # --- Phase 9 advisory indicators (never affect the ML prediction) ---
    ood_status = Column(String, nullable=True)
    review_priority = Column(String, nullable=True)
    # Snapshot of the intelligence layer + signals for the reviewer workflow.
    intelligence_json = Column(Text, nullable=True)
    # --- Phase 10 extraction diagnostics (JSON) ---
    extraction_metadata = Column(Text, nullable=True)
    # --- Phase 12 evidence engine (JSON): final assessment + evidence items ---
    evidence_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    certificate = relationship("Certificate")