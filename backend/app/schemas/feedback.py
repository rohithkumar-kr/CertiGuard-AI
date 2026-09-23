"""Pydantic schemas for the feedback API (Phase 9B/9I)."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.feedback import REVIEWER_LABELS


class FeedbackCreate(BaseModel):
    reviewer_label: str = Field(min_length=1, max_length=30)
    reviewer_note: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("reviewer_label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        if value not in REVIEWER_LABELS:
            raise ValueError(
                f"reviewer_label must be one of: {', '.join(REVIEWER_LABELS)}."
            )
        return value


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    verification_id: str
    reviewer_label: str
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    original_prediction: str
    original_risk_score: float
    model_version: Optional[str] = None
    certificate_type: Optional[str] = None
    extraction_completeness: Optional[float] = None
    review_status: Optional[str] = None
    ood_status: Optional[str] = None
    review_priority: Optional[str] = None
    is_disagreement: Optional[bool] = None
    split: Optional[str] = None
    dataset_batch: Optional[str] = None


class FeedbackSummaryResponse(BaseModel):
    total_reviewed: int
    not_reviewed: int
    confirmed_genuine: int
    confirmed_suspicious: int
    uncertain: int
    decisive_reviews: int
    agreement_count: int
    disagreement_count: int
    agreement_rate: Optional[float] = None
    disagreement_rate: Optional[float] = None


class FeedbackAnalyticsResponse(BaseModel):
    summary: FeedbackSummaryResponse
    overall: dict[str, Any]
    by_certificate_type: dict[str, Any]
    by_issuer: dict[str, Any]
    by_review_status: dict[str, Any]
    by_priority: dict[str, Any]
    by_extraction_completeness: dict[str, Any]
    average_extraction_completeness: Optional[float] = None
    ood_distribution: dict[str, int]
    review_priority_distribution: dict[str, int]
    manual_review_rate: Optional[float] = None
    minimum_metric_samples: int