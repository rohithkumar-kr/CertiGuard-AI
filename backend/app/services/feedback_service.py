"""Feedback recording and analytics service (Phase 9).

This service is the single place that:

  - validates and records a human-review decision (9A/9B)
  - exposes the feedback summary (9B)
  - computes the feedback analytics view (9I)

It never modifies the ML model, threshold, or feature schema. Feedback rows are
immutable evidence; updating a decision is intentionally not supported to keep
the audit trail unambiguous.
"""

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.feedback import QUALIFYING_LABELS, REVIEWER_LABELS, VerificationFeedback
from app.models.verification import Verification
from app.services import audit_service

logger = get_logger("feedback_service")

# Minimum number of decisive samples before a percentage metric is reported.
# Below this we report "insufficient samples" instead of a misleading number.
MIN_METRIC_SAMPLES = 10
MIN_GROUP_SAMPLES = 5

_QUALIFYING_SET = set(QUALIFYING_LABELS)
_LABEL_SET = set(REVIEWER_LABELS)


def _primary_cert_type(verification: Verification) -> str | None:
    """Return the intelligence primary certificate type from the persisted
    JSON certificate-type flags (best-effort)."""
    raw = verification.certificate_type
    if not raw:
        return None
    try:
        flags = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(flags, dict):
        return None
    for name in ("academic", "technical", "training", "completion", "online", "workshop"):
        if flags.get(name):
            return name
    return None


def _extraction_completeness(verification: Verification) -> float | None:
    """Recompute extraction completeness from the persisted extracted_info."""
    raw = verification.extracted_info
    if not raw:
        return None
    try:
        fields = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(fields, dict):
        return None
    keys = ("candidate_name", "organization", "course", "issue_date", "cert_id")
    present = sum(1 for k in keys if fields.get(k) and str(fields.get(k)).strip())
    return round(present / len(keys), 4)


def _is_disagreement(label: str, prediction: str) -> bool:
    """A decisive reviewer label that contradicts the AI prediction."""
    if label == "confirmed_genuine":
        return prediction != "genuine"
    if label == "confirmed_suspicious":
        return prediction != "suspicious"
    return False


def _evidence_snapshot(verification: Verification) -> dict:
    """Phase 12 evidence snapshot from the persisted evidence_json."""
    raw = verification.evidence_json
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    ve = value.get("verification_evidence") or {}
    anomaly = value.get("anomaly") or {}
    return {
        "final_assessment": ve.get("assessment"),
        "anomaly_score": anomaly.get("score"),
        "anomaly_level": anomaly.get("level"),
    }


def record_feedback(
    db: Session,
    verification_id: str,
    reviewer_label: str,
    reviewer_note: str | None = None,
) -> VerificationFeedback:
    """Record a reviewer decision for a verification.

    Raises AppError for:
      - unknown verification
      - invalid reviewer label
      - a verification that errored (nothing to review)
      - an already-reviewed verification (duplicate submission)
    """
    if reviewer_label not in _LABEL_SET:
        raise AppError(
            f"Invalid reviewer label. Expected one of: {', '.join(REVIEWER_LABELS)}."
        )

    verification = (
        db.query(Verification)
        .filter(Verification.verification_id == verification_id)
        .first()
    )
    if verification is None:
        raise AppError("Verification not found.")
    if verification.prediction == "error":
        raise AppError("A failed verification cannot be reviewed.")

    existing = (
        db.query(VerificationFeedback)
        .filter(VerificationFeedback.verification_id == verification_id)
        .first()
    )
    if existing is not None:
        raise AppError("This verification has already been reviewed.")

    note = (reviewer_note or "").strip()
    evidence = _evidence_snapshot(verification)
    feedback = VerificationFeedback(
        verification_id=verification.verification_id,
        reviewer_label=reviewer_label,
        reviewer_note=note or None,
        original_prediction=verification.prediction,
        original_risk_score=verification.risk_score,
        original_confidence=verification.confidence,
        model_version=verification.model_version,
        certificate_type=_primary_cert_type(verification),
        extraction_completeness=_extraction_completeness(verification),
        review_status=verification.review_status,
        issuer=verification.issuer,
        ood_status=verification.ood_status,
        review_priority=verification.review_priority,
        file_fingerprint=verification.file_fingerprint,
        cert_id_fingerprint=verification.cert_id_fingerprint,
        identity_fingerprint=verification.identity_fingerprint,
        is_disagreement=_is_disagreement(reviewer_label, verification.prediction),
        # --- Phase 12 evidence-engine snapshot ---
        final_assessment=evidence.get("final_assessment"),
        anomaly_score=evidence.get("anomaly_score"),
        anomaly_level=evidence.get("anomaly_level"),
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    _record_review_event(db, verification_id, reviewer_label, feedback, verification)
    logger.info(
        "Feedback recorded: verification=%s label=%s disagreement=%s",
        verification_id, reviewer_label, feedback.is_disagreement,
    )
    return feedback


def _record_review_event(db: Session, verification_id: str, reviewer_label: str,
                         feedback: VerificationFeedback,
                         verification: Verification) -> None:
    """Append the REVIEW_ACTION audit event (best-effort)."""
    try:
        audit_service.record_event(
            db,
            verification_id=verification_id,
            event_type=audit_service.EVENT_REVIEW_ACTION,
            stage="review",
            status=audit_service.STATUS_RECORDED,
            severity={
                "confirmed_genuine": audit_service.SEVERITY_SUCCESS,
                "uncertain": audit_service.SEVERITY_WARNING,
                "confirmed_suspicious": audit_service.SEVERITY_ERROR,
            }.get(reviewer_label, audit_service.SEVERITY_INFO),
            title="Review decision recorded",
            description=f"Reviewer decision recorded as '{reviewer_label}'.",
            details={
                "reviewer_label": reviewer_label,
                "is_disagreement": feedback.is_disagreement,
                "original_prediction": verification.prediction,
                "original_risk_score": verification.risk_score,
                "model_version": verification.model_version,
                "reviewer_note": feedback.reviewer_note,
            },
        )
    except Exception:  # noqa: BLE001 - audit must never break feedback recording
        db.rollback()
        logger.exception("Could not record review audit event")


def feedback_summary(db: Session) -> dict:
    """Summary counts over the feedback collection (9B)."""
    rows = db.query(VerificationFeedback).all()
    by_label: dict[str, int] = {}
    for row in rows:
        by_label[row.reviewer_label] = by_label.get(row.reviewer_label, 0) + 1

    total_reviewed = len(rows)
    decisive = sum(by_label.get(l, 0) for l in QUALIFYING_LABELS)
    disagreements = sum(1 for r in rows if r.is_disagreement)

    # not_reviewed = successful verifications without a feedback row.
    successful = db.query(Verification).filter(Verification.prediction != "error").count()

    summary = {
        "total_reviewed": total_reviewed,
        "not_reviewed": max(successful - total_reviewed, 0),
        "confirmed_genuine": by_label.get("confirmed_genuine", 0),
        "confirmed_suspicious": by_label.get("confirmed_suspicious", 0),
        "uncertain": by_label.get("uncertain", 0),
        "decisive_reviews": decisive,
        "agreement_count": decisive - disagreements,
        "disagreement_count": disagreements,
    }
    if decisive:
        summary["agreement_rate"] = round(
            (decisive - disagreements) / decisive, 4
        )
        summary["disagreement_rate"] = round(disagreements / decisive, 4)
    else:
        summary["agreement_rate"] = None
        summary["disagreement_rate"] = None
    return summary


def _aggregate(rows: list[VerificationFeedback]) -> dict:
    """Group metrics for a list of decisive feedback rows.

    Treats confirmed_genuine as the positive class for the confusion matrix so
    "genuine recall" is meaningful; suspicious counts are derived from it.
    """
    total = len(rows)
    genuine_truth = sum(1 for r in rows if r.reviewer_label == "confirmed_genuine")
    suspicious_truth = total - genuine_truth
    genuine_pred = sum(1 for r in rows if r.original_prediction == "genuine")
    suspicious_pred = total - genuine_pred

    tp = sum(
        1 for r in rows
        if r.reviewer_label == "confirmed_genuine" and r.original_prediction == "genuine"
    )
    tn = sum(
        1 for r in rows
        if r.reviewer_label == "confirmed_suspicious" and r.original_prediction == "suspicious"
    )
    fp = genuine_pred - tp
    fn = suspicious_truth - tn

    out = {
        "n": total,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "genuine_truth": genuine_truth,
        "suspicious_truth": suspicious_truth,
        "genuine_pred": genuine_pred,
        "suspicious_pred": suspicious_pred,
    }
    if total < MIN_METRIC_SAMPLES:
        out["sufficient"] = False
        return out
    out["sufficient"] = True
    out["genuine_precision"] = round(tp / genuine_pred, 4) if genuine_pred else None
    out["genuine_recall"] = round(tp / genuine_truth, 4) if genuine_truth else None
    out["genuine_f1"] = _f1(tp, fp, fn)
    out["suspicious_precision"] = round(tn / suspicious_pred, 4) if suspicious_pred else None
    out["suspicious_recall"] = round(tn / suspicious_truth, 4) if suspicious_truth else None
    out["suspicious_f1"] = _f1(tn, fn, fp)
    out["false_positive_rate"] = round(fp / (fp + tn), 4) if (fp + tn) else None
    out["false_negative_rate"] = round(fn / (fn + tp), 4) if (fn + tp) else None
    out["accuracy"] = round((tp + tn) / total, 4)
    out["disagreement_count"] = sum(1 for r in rows if r.is_disagreement)
    return out


def _f1(tp: int, fp: int, fn: int) -> float | None:
    denom = 2 * tp + fp + fn
    return round(2 * tp / denom, 4) if denom else None


def feedback_analytics(db: Session) -> dict:
    """Monitoring/analytics view over reviewed certificates (9I).

    Percentages are only reported when the underlying sample count is high
    enough; otherwise the metric is reported as "insufficient samples".
    """
    rows = db.query(VerificationFeedback).all()
    reviewed = [r for r in rows if r.reviewer_label in _LABEL_SET]
    decisive = [r for r in reviewed if r.reviewer_label in _QUALIFYING_SET]

    summary = feedback_summary(db)
    overall = _aggregate(decisive)

    def _per_group(rows_: list, key_attr: str) -> dict:
        groups: dict[str, list] = {}
        for r in rows_:
            key = getattr(r, key_attr)
            label = key if key and str(key).strip() else "unknown"
            groups.setdefault(label, []).append(r)
        return {
            label: _aggregate(items)
            for label, items in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
        }

    def _averages(rows_: list, attr: str) -> float | None:
        values = [getattr(r, attr) for r in rows_ if getattr(r, attr) is not None]
        return round(sum(values) / len(values), 4) if values else None

    ood_counter: dict[str, int] = {}
    for r in reviewed:
        ood_counter[r.ood_status or "unknown"] = ood_counter.get(r.ood_status or "unknown", 0) + 1

    priority_counter: dict[str, int] = {}
    for r in reviewed:
        priority_counter[r.review_priority or "unknown"] = (
            priority_counter.get(r.review_priority or "unknown", 0) + 1
        )

    total_successful = db.query(Verification).filter(Verification.prediction != "error").count()

    return {
        "summary": summary,
        "overall": overall,
        "by_certificate_type": _per_group(decisive, "certificate_type"),
        "by_issuer": _per_group(decisive, "issuer"),
        "by_review_status": _per_group(decisive, "review_status"),
        "by_priority": _per_group(decisive, "review_priority"),
        "by_extraction_completeness": _aggregate_completeness_buckets(decisive),
        "average_extraction_completeness": _averages(reviewed, "extraction_completeness"),
        "ood_distribution": ood_counter,
        "review_priority_distribution": priority_counter,
        "manual_review_rate": (
            round(summary["total_reviewed"] / total_successful, 4) if total_successful else None
        ),
        "minimum_metric_samples": MIN_METRIC_SAMPLES,
    }


def _aggregate_completeness_buckets(rows: list) -> dict:
    """Split extraction completeness into low (<0.4) / medium (<0.8) / high."""
    buckets = {"low": [], "medium": [], "high": [], "unknown": []}
    for r in rows:
        value = r.extraction_completeness
        if value is None:
            buckets["unknown"].append(r)
        elif value < 0.4:
            buckets["low"].append(r)
        elif value < 0.8:
            buckets["medium"].append(r)
        else:
            buckets["high"].append(r)
    return {k: _aggregate(v) for k, v in buckets.items()}