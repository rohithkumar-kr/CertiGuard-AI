"""Phase 12 validation reporting (M13).

Builds the Phase 12 evidence-engine evaluation report from reviewer-labeled
verifications in the database:

  * assessment distribution (LIKELY_GENUINE / LIKELY_SUSPICIOUS /
    REQUIRES_VERIFICATION / INSUFFICIENT_EVIDENCE)
  * confusion matrix of the evidence-engine assessment vs reviewer ground truth
  * accuracy / precision / recall / F1 / FPR / FNR for the decisive
    (genuine vs suspicious) verdicts
  * manual-review rate
  * breakdowns by certificate type, extraction method, OOD status, risk band
    and issuer
  * a separate list of false positives and false negatives with the failure
    reason (which evidence categories disagreed with the reviewer)
  * the ML model comparison (prediction vs truth) for context

Metrics with too few decisive samples are reported as "insufficient samples".

Usage:
    python scripts/generate_phase12_report.py [--output monitoring/phase12_report.json]
"""

import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import func  # noqa: E402

from app.database.database import SessionLocal, init_db  # noqa: E402
from app.models.feedback import QUALIFYING_LABELS  # noqa: E402
from app.models.verification import Verification  # noqa: E402
from app.models.feedback import VerificationFeedback  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIN_DECISIVE_SAMPLES = 5


def _load_pairs(db):
    """Load (verification, feedback) pairs with the persisted evidence."""
    rows = (
        db.query(Verification, VerificationFeedback)
        .join(VerificationFeedback, VerificationFeedback.verification_id == Verification.verification_id)
        .all()
    )
    pairs = []
    for ver, fb in rows:
        evidence = {}
        if ver.evidence_json:
            try:
                evidence = json.loads(ver.evidence_json)
            except (ValueError, TypeError):
                evidence = {}
        ve = evidence.get("verification_evidence") or {}
        pairs.append({
            "verification_id": ver.verification_id,
            "truth": fb.reviewer_label,
            "ml_prediction": ver.prediction,
            "risk_score": ver.risk_score,
            "assessment": ve.get("assessment") or "REQUIRES_VERIFICATION",
            "assessment_conf": ve.get("confidence"),
            "category_status": ve.get("category_status") or {},
            "issuer": ver.issuer,
            "certificate_type": fb.certificate_type,
            "extraction_method": None,
            "ood_status": ver.ood_status,
            "anomaly_level": (evidence.get("anomaly") or {}).get("level"),
            "evidence_items": ve.get("evidence_items") or [],
        })
    return pairs


def _to_binary(pairs):
    """Reduce pairs to decisive (genuine vs suspicious) assessments + truth."""
    truth_map = {"confirmed_genuine": "genuine", "confirmed_suspicious": "suspicious"}
    decisive = []
    for p in pairs:
        if p["truth"] not in truth_map:
            continue
        ass = p["assessment"]
        binary = None
        if ass == "LIKELY_GENUINE":
            binary = "genuine"
        elif ass == "LIKELY_SUSPICIOUS":
            binary = "suspicious"
        if binary is None:
            continue
        decisive.append({
            **p,
            "truth": truth_map[p["truth"]],
            "assessment": binary,
            "ml_prediction": p["ml_prediction"],
            "verification_id": p["verification_id"],
        })
    return decisive


def _confusion_matrix(decisive):
    tp = sum(1 for p in decisive if p["truth"] == "genuine" and p["assessment"] == "genuine")
    tn = sum(1 for p in decisive if p["truth"] == "suspicious" and p["assessment"] == "suspicious")
    fp = sum(1 for p in decisive if p["truth"] == "suspicious" and p["assessment"] == "genuine")
    fn = sum(1 for p in decisive if p["truth"] == "genuine" and p["assessment"] == "suspicious")
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "n": len(decisive)}


def _metrics(cm):
    if cm["n"] < MIN_DECISIVE_SAMPLES:
        return {"sufficient": False, "n": cm["n"]}
    tp, tn, fp, fn = cm["tp"], cm["tn"], cm["fp"], cm["fn"]
    n = tp + tn + fp + fn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    specificity = tn / (tn + fp) if (tn + fp) else None
    return {
        "sufficient": True,
        "n": n,
        "accuracy": round((tp + tn) / n, 4),
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "f1": round(f1, 4) if f1 is not None else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else None,
        "false_negative_rate": round(fn / (fn + tp), 4) if (fn + tp) else None,
        "confusion_matrix": cm,
    }


def _group_breakdown(decisive, key):
    groups = {}
    for p in decisive:
        k = p.get(key) or "unknown"
        groups.setdefault(k, []).append(p)
    out = {}
    for k, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        cm = _confusion_matrix(items)
        out[k] = {"n": len(items), **_metrics(cm)}
    return out


def _ml_confusion_matrix(decisive):
    tp = sum(1 for p in decisive if p["truth"] == "genuine" and p["ml_prediction"] == "genuine")
    tn = sum(1 for p in decisive if p["truth"] == "suspicious" and p["ml_prediction"] == "suspicious")
    fp = sum(1 for p in decisive if p["truth"] == "suspicious" and p["ml_prediction"] == "genuine")
    fn = sum(1 for p in decisive if p["truth"] == "genuine" and p["ml_prediction"] == "suspicious")
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn, "n": len(decisive)}


def _risk_band(risk):
    if risk >= 0.5:
        return "high (>=0.5)"
    if risk >= 0.3:
        return "elevated (0.3-0.5)"
    return "low (<0.3)"


def _failure_reason(p):
    """Summarize which evidence categories disagreed with the reviewer."""
    cat = p["category_status"]
    reasons = []
    if p["truth"] == "genuine" and p["assessment"] == "suspicious":
        for c, status in cat.items():
            if status == "FAIL":
                reasons.append(f"{c}:FAIL")
        reasons.append(f"risk={p['risk_score']:.3f}")
    elif p["truth"] == "suspicious" and p["assessment"] == "genuine":
        for c, status in cat.items():
            if status == "PASS":
                reasons.append(f"{c}:PASS")
        reasons.append(f"anomaly={p.get('anomaly_level')}")
    return "; ".join(reasons) or "reviewer disagreed with assessment"


def generate_report(db) -> dict:
    pairs = _load_pairs(db)
    decisive = _to_binary(pairs)
    cm = _confusion_matrix(decisive)
    ml_cm = _ml_confusion_matrix(decisive)

    # Assessment distribution over ALL reviewed pairs (including uncertain).
    distribution = {}
    for p in pairs:
        distribution[p["assessment"]] = distribution.get(p["assessment"], 0) + 1

    fns = [p for p in decisive if p["truth"] == "genuine" and p["assessment"] == "suspicious"]
    fps = [p for p in decisive if p["truth"] == "suspicious" and p["assessment"] == "genuine"]

    total_verifications = db.query(Verification).filter(Verification.prediction != "error").count()

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "reviewed_count": len(pairs),
        "decisive_count": len(decisive),
        "total_verifications": total_verifications,
        "manual_review_rate": round(len(pairs) / total_verifications, 4) if total_verifications else None,
        "assessment_distribution": distribution,
        "evidence_engine": {
            "confusion_matrix": cm,
            **_metrics(cm),
        },
        "ml_model": {
            "confusion_matrix": ml_cm,
            **_metrics(ml_cm),
        },
        "by_certificate_type": _group_breakdown(decisive, "certificate_type"),
        "by_ood_status": _group_breakdown(decisive, "ood_status"),
        "by_risk_band": _group_breakdown(
            [{**p, "risk_band": _risk_band(p["risk_score"])} for p in decisive],
            "risk_band",
        ),
        "by_issuer": _group_breakdown(decisive, "issuer"),
        "false_positives": [
            {"verification_id": p["verification_id"], "issuer": p["issuer"],
             "risk": round(p["risk_score"], 3), "reason": _failure_reason(p)}
            for p in fps
        ],
        "false_negatives": [
            {"verification_id": p["verification_id"], "issuer": p["issuer"],
             "risk": round(p["risk_score"], 3), "reason": _failure_reason(p)}
            for p in fns
        ],
        "minimum_decisive_samples": MIN_DECISIVE_SAMPLES,
    }


def main():
    output = ROOT / "monitoring" / "phase12_report.json"
    if len(sys.argv) > 1 and sys.argv[1].startswith("--output="):
        output = ROOT / sys.argv[1].split("=", 1)[1]

    init_db()
    db = SessionLocal()
    try:
        report = generate_report(db)
    finally:
        db.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    ee = report["evidence_engine"]
    ml = report["ml_model"]
    print(f"Reviewed: {report['reviewed_count']}  decisive: {report['decisive_count']}")
    print(f"Assessment distribution: {report['assessment_distribution']}")
    print(f"Evidence engine: {ee}")
    print(f"ML model: {ml}")
    print(f"FPs: {len(report['false_positives'])}  FNs: {len(report['false_negatives'])}")
    print(f"\nReport written to {output}")


if __name__ == "__main__":
    main()