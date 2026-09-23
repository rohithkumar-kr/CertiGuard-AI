"""Pydantic response schemas returned by the API."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class VerificationEvidence(BaseModel):
    """Phase 12 evidence engine block (additive, backward compatible)."""

    assessment: str = "REQUIRES_VERIFICATION"
    confidence: float = 0.5
    recommended_action: str = "manual_verification"
    category_status: dict[str, str] = {}
    summary: dict[str, Any] = {}
    evidence_items: list[dict[str, Any]] = []

    # --- upgrade: 4-state decision vocabulary ---
    decision: str = "REQUIRES_VERIFICATION"
    next_action: str = "manual_verification"
    decision_summary: str = ""


class IssuerVerification(BaseModel):
    """Issuer-side verification result for a credential (advisory).

    ``status`` is one of:
        VERIFIED_BY_ISSUER | NOT_VERIFIED | VERIFICATION_UNAVAILABLE | ISSUER_UNKNOWN

    ``checked_identifiers`` are always masked. ``VERIFICATION_UNAVAILABLE``
    means no authoritative issuer check was possible — never a fraud signal.
    """

    status: str = "VERIFICATION_UNAVAILABLE"
    issuer: Optional[str] = None
    verification_method: Optional[str] = None
    verification_url: Optional[str] = None
    checked_identifiers: list[str] = []
    source: str = "none"
    reason: str = ""
    confidence: float = 0.0
    timestamp: Optional[str] = None
    error_reason: Optional[str] = None


class VerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_id: str
    prediction: str
    label: str
    risk_score: float
    confidence: float
    message: str
    model_version: str
    certificate_type: dict[str, Any] = {}
    explanation: list[dict[str, Any]] = []
    extracted: dict[str, Any] = {}
    warnings: list[str] = []
    created_at: Optional[datetime] = None

    # --- Phase 8 intelligence ---
    review_status: str = "low_risk"
    recommended_action: dict[str, Any] = {}
    intelligence: dict[str, Any] = {}
    positive_signals: list[dict[str, Any]] = []
    risk_signals: list[dict[str, Any]] = []
    duplicate: dict[str, Any] = {}

    # --- Phase 9 advisory indicators ---
    ood_status: Optional[str] = None
    review_priority: Optional[str] = None
    extraction_completeness: Optional[float] = None

    # --- Phase 10 extraction diagnostics ---
    extraction: dict[str, Any] = {}

    # --- Phase 12 evidence engine ---
    verification_evidence: VerificationEvidence = VerificationEvidence()

    # --- upgrade: issuer verification (advisory, additive) ---
    issuer_verification: IssuerVerification = IssuerVerification()

    # --- upgrade: decision surfaced at the top level (additive) ---
    decision: str = ""
    decision_summary: str = ""
    next_action: str = ""


class VerificationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_id: str
    filename: Optional[str] = None
    prediction: str
    risk_score: float
    confidence: float
    model_version: str
    created_at: Optional[datetime] = None

    # --- Phase 8 intelligence ---
    review_status: Optional[str] = None
    issuer: Optional[str] = None
    certificate_type: Optional[str] = None
    duplicate_of: Optional[str] = None
    duplicate_type: Optional[str] = None

    # --- Phase 9 advisory indicators + review status ---
    ood_status: Optional[str] = None
    review_priority: Optional[str] = None
    extraction_completeness: Optional[float] = None
    reviewer_label: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    is_disagreement: Optional[bool] = None


class VerificationDetailResponse(BaseModel):
    """Full detail for a single verification (reviewer workflow, 9H)."""

    model_config = ConfigDict(from_attributes=True)

    verification_id: str
    filename: Optional[str] = None
    prediction: str
    label: Optional[str] = None
    risk_score: float
    confidence: float
    model_version: str
    created_at: Optional[datetime] = None
    error: Optional[str] = None

    # --- Phase 8 intelligence ---
    review_status: Optional[str] = None
    issuer: Optional[str] = None
    certificate_type: Optional[str] = None
    extracted_info: Optional[str] = None
    duplicate_of: Optional[str] = None
    duplicate_type: Optional[str] = None

    # --- Phase 9 advisory indicators ---
    ood_status: Optional[str] = None
    review_priority: Optional[str] = None
    extraction_completeness: Optional[float] = None
    intelligence: dict[str, Any] = {}
    positive_signals: list[dict[str, Any]] = []
    risk_signals: list[dict[str, Any]] = []
    duplicate: dict[str, Any] = {}

    # --- Phase 10 extraction diagnostics ---
    extraction: dict[str, Any] = {}

    # --- Feedback ---
    reviewer_label: Optional[str] = None
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    is_disagreement: Optional[bool] = None

    # --- Phase 12 evidence engine ---
    verification_evidence: VerificationEvidence = VerificationEvidence()
    evidence_details: dict[str, Any] = {}

    # --- upgrade: issuer verification (advisory, additive) ---
    issuer_verification: IssuerVerification = IssuerVerification()


class HealthResponse(BaseModel):
    status: str
    app: str
    model_version: Optional[str] = None
    model_loaded: bool


class ModelInfoResponse(BaseModel):
    model_version: str
    model_name: str
    features: list[str]
    metrics: dict[str, Any] = {}
    created_at: Optional[str] = None


class MetricsResponse(BaseModel):
    total_verifications: int
    genuine_count: int
    suspicious_count: int
    error_count: int
    prediction_distribution: dict[str, int]
    certificate_type_distribution: dict[str, int]
    average_risk_score: float
    average_confidence: float
    model_versions: dict[str, int]
    recent: list[VerificationRecord]

    # --- Phase 8 monitoring ---
    review_status_distribution: dict[str, int] = {}
    average_extraction_completeness: float = 0.0
    issuer_distribution: dict[str, int] = {}
    manual_review_rate: float = 0.0


class VerificationSummary(BaseModel):
    total: int
    genuine_count: int
    suspicious_count: int
    manual_review_count: int
    average_risk_score: float


class AuditEvent(BaseModel):
    """One append-only event in a verification's audit trail."""

    id: int
    verification_id: str
    event_type: str
    stage: Optional[str] = None
    status: str
    severity: str
    title: str
    description: Optional[str] = None
    details: dict[str, Any] = {}
    created_at: Optional[datetime] = None


class AuditTrailResponse(BaseModel):
    """The chronological investigation timeline for a verification."""

    verification_id: str
    events: list[AuditEvent] = []


class ErrorResponse(BaseModel):
    detail: str