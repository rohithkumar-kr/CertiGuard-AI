"""Model error analysis over reviewed certificates (Phase 9C).

Compares the AI prediction against the human-review decision (ground truth)
for reviewed certificates and reports:

  - confusion matrix (AI prediction vs reviewer truth)
  - precision / recall / F1 (for both genuine and suspicious)
  - false-positive rate and false-negative rate
  - model/reviewer disagreement
  - performance by certificate type, issuer, review status, priority and
    extraction-completeness bucket

When a metric's underlying sample count is too small it is reported as
"insufficient samples" instead of a made-up number. No statistics are invented.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.feedback import QUALIFYING_LABELS, VerificationFeedback
from src.feedback.labels import MIN_GROUP_SAMPLES, MIN_METRIC_SAMPLES

logger = get_logger("feedback_analysis")

INSUFFICIENT = "insufficient samples"

TRUTH_LABEL = {"confirmed_genuine": "genuine", "confirmed_suspicious": "suspicious"}


def _load_decisive(db: Session) -> list[VerificationFeedback]:
    return (
        db.query(VerificationFeedback)
        .filter(VerificationFeedback.reviewer_label.in_(QUALIFYING_LABELS))
        .all()
    )


def _confusion(rows: list) -> tuple[int, int, int, int]:
    """(tp, fp, fn, tn) with 'genuine' treated as positive."""
    tp = sum(1 for r in rows if r.reviewer_label == "confirmed_genuine" and r.original_prediction == "genuine")
    fp = sum(1 for r in rows if r.reviewer_label == "confirmed_suspicious" and r.original_prediction == "genuine")
    fn = sum(1 for r in rows if r.reviewer_label == "confirmed_genuine" and r.original_prediction == "suspicious")
    tn = sum(1 for r in rows if r.reviewer_label == "confirmed_suspicious" and r.original_prediction == "suspicious")
    return tp, fp, fn, tn


def _f1(tp: int, fp: int, fn: int):
    denom = 2 * tp + fp + fn
    return round(2 * tp / denom, 4) if denom else None


def _safe_ratio(num: int, den: int):
    return round(num / den, 4) if den else None


def _metrics(rows: list, min_samples: int) -> dict:
    """Full metric block for a group of decisive rows."""
    if len(rows) < min_samples:
        return {
            "n": len(rows),
            "sufficient": False,
            "note": INSUFFICIENT,
        }
    tp, fp, fn, tn = _confusion(rows)
    genuine_truth = tp + fn
    suspicious_truth = fp + tn
    genuine_pred = tp + fp
    suspicious_pred = fn + tn

    out = {
        "n": len(rows),
        "sufficient": True,
        "confusion_matrix": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        },
        "genuine_precision": _safe_ratio(tp, genuine_pred),
        "genuine_recall": _safe_ratio(tp, genuine_truth),
        "genuine_f1": _f1(tp, fp, fn),
        "suspicious_precision": _safe_ratio(tn, suspicious_pred),
        "suspicious_recall": _safe_ratio(tn, suspicious_truth),
        "suspicious_f1": _f1(tn, fn, fp),
        "false_positive_rate": _safe_ratio(fp, fp + tn),
        "false_negative_rate": _safe_ratio(fn, fn + tp),
        "accuracy": round((tp + tn) / len(rows), 4),
        "disagreement_count": sum(1 for r in rows if r.is_disagreement),
    }
    return out


def _group_by(rows: list, attr: str) -> dict:
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        value = getattr(r, attr)
        key = value if value and str(value).strip() else "unknown"
        groups[key].append(r)
    return {
        label: _metrics(items, MIN_GROUP_SAMPLES)
        for label, items in sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    }


def _completeness_buckets(rows: list) -> dict:
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        value = r.extraction_completeness
        if value is None:
            buckets["unknown"].append(r)
        elif value < 0.4:
            buckets["low (<0.4)"].append(r)
        elif value < 0.8:
            buckets["medium (0.4-0.8)"].append(r)
        else:
            buckets["high (>=0.8)"].append(r)
    return {label: _metrics(items, MIN_GROUP_SAMPLES) for label, items in buckets.items()}


def analyze_feedback(db: Session) -> dict:
    """Run the full error analysis over reviewed certificates."""
    decisive = _load_decisive(db)
    overall = _metrics(decisive, MIN_METRIC_SAMPLES)
    by_cert_type = _group_by(decisive, "certificate_type")
    by_issuer = _group_by(decisive, "issuer")
    by_review_status = _group_by(decisive, "review_status")
    by_priority = _group_by(decisive, "review_priority")
    by_completeness = _completeness_buckets(decisive)

    total_disagreements = sum(1 for r in decisive if r.is_disagreement)
    return {
        "n_reviewed_decisive": len(decisive),
        "n_disagreements": total_disagreements,
        "disagreement_rate": (
            round(total_disagreements / len(decisive), 4) if decisive else None
        ),
        "min_metric_samples": MIN_METRIC_SAMPLES,
        "min_group_samples": MIN_GROUP_SAMPLES,
        "overall": overall,
        "by_certificate_type": by_cert_type,
        "by_issuer": by_issuer,
        "by_review_status": by_review_status,
        "by_review_priority": by_priority,
        "by_extraction_completeness": by_completeness,
    }


def format_analysis(report: dict) -> str:
    """Human-readable rendering of the analysis report."""
    lines = [f"Reviewed decisive samples: {report['n_reviewed_decisive']}",
             f"Model/reviewer disagreements: {report['n_disagreements']}"]

    def _render_block(title: str, block: dict) -> None:
        lines.append(f"\n--- {title} ---")
        if not block.get("sufficient", False):
            lines.append(f"  {block.get('note', INSUFFICIENT)} (n={block.get('n', 0)})")
            return
        cm = block["confusion_matrix"]
        lines.append(f"  confusion matrix (genuine=positive): "
                     f"TP={cm['tp']} FP={cm['fp']} FN={cm['fn']} TN={cm['tn']}")
        lines.append(f"  genuine precision={block['genuine_precision']} recall={block['genuine_recall']} f1={block['genuine_f1']}")
        lines.append(f"  suspicious precision={block['suspicious_precision']} recall={block['suspicious_recall']} f1={block['suspicious_f1']}")
        lines.append(f"  false positive rate={block['false_positive_rate']} false negative rate={block['false_negative_rate']}")
        lines.append(f"  accuracy={block['accuracy']} disagreements={block['disagreement_count']}")

    _render_block("OVERALL", report["overall"])
    for title, block in report["by_certificate_type"].items():
        _render_block(f"certificate type: {title}", block)
    for title, block in report["by_issuer"].items():
        _render_block(f"issuer: {title}", block)
    for title, block in report["by_review_status"].items():
        _render_block(f"review status: {title}", block)
    for title, block in report["by_review_priority"].items():
        _render_block(f"review priority: {title}", block)
    for title, block in report["by_extraction_completeness"].items():
        _render_block(f"extraction completeness: {title}", block)
    return "\n".join(lines)