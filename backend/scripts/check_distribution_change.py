"""Detect distribution change (drift) in production verifications.

Reads the recorded verification rows from the local database and compares the
current prediction / certificate-type / risk-score distributions against a
baseline snapshot stored locally (monitoring/distribution_baseline.json).

This is a fully local, no-cloud drift monitor. It reports:

  - prediction distribution (genuine/suspicious/error) vs baseline
  - certificate-type distribution vs baseline
  - risk-score statistics (mean, p95) vs baseline
  - a symmetric JSD-like relative shift for each categorical distribution

Exit code 0 = no meaningful drift, 1 = drift detected. Use --update-baseline
after confirming the current traffic is the intended steady state.

Examples:
  python scripts/check_distribution_change.py
  python scripts/check_distribution_change.py --update-baseline
  python scripts/check_distribution_change.py --report monitoring/distribution_report.json
"""

import argparse
import json
import math
import pathlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.database.database import SessionLocal  # noqa: E402
from app.models.verification import Verification  # noqa: E402

DEFAULT_BASELINE = Path(__file__).resolve().parent.parent / "monitoring" / "distribution_baseline.json"
DEFAULT_REPORT = Path(__file__).resolve().parent.parent / "monitoring" / "distribution_report.json"


def _log2(p: float) -> float:
    return math.log2(p) if p > 0 else 0.0


def _kl(a: Counter, b: Counter) -> float:
    """Kullback-Leibler divergence D_KL(a || b) over the union of keys."""
    keys = set(a) | set(b)
    total_a = sum(a.values()) or 1
    total_b = sum(b.values()) or 1
    pa = {k: (a.get(k, 0) / total_a) for k in keys}
    pb = {k: (b.get(k, 0) / total_b) for k in keys}
    return sum(pa[k] * _log2(pa[k] / pb[k]) if pb[k] > 0 else 0.0 for k in keys)


def _jsd(a: Counter, b: Counter) -> float:
    """Jensen-Shannon distance (symmetric, bounded [0,1])."""
    keys = set(a) | set(b)
    total_a = sum(a.values()) or 1
    total_b = sum(b.values()) or 1
    pa = {k: (a.get(k, 0) / total_a) for k in keys}
    pb = {k: (b.get(k, 0) / total_b) for k in keys}
    pm = {k: (pa[k] + pb[k]) / 2.0 for k in keys}
    return math.sqrt((_kl(Counter(pa), Counter(pm)) + _kl(Counter(pb), Counter(pm))) / 2.0)


def _extract_cert_types(rows):
    flags: Counter = Counter()
    for r in rows:
        if not r.certificate_type:
            continue
        try:
            parsed = json.loads(r.certificate_type)
        except (ValueError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        for name, value in parsed.items():
            if value:
                flags[name] += 1
    return flags


def _extraction_completeness(record) -> float:
    """Fraction of key identity fields present in the persisted extracted_info."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="Baseline snapshot file (created with --update-baseline)")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT,
                        help="Where to write the drift report JSON")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Snapshot the current distribution as the new baseline")
    parser.add_argument("--jsd-threshold", type=float, default=0.25,
                        help="JSD above which a categorical distribution is flagged")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.query(Verification).all()
    finally:
        db.close()

    successful = [r for r in rows if r.prediction != "error"]
    prediction_dist = Counter(r.prediction for r in successful)
    review_status_dist = Counter(r.review_status or "low_risk" for r in successful)
    cert_type_dist = _extract_cert_types(successful)
    risk_scores = sorted(r.risk_score for r in successful)
    risk_mean = round(sum(risk_scores) / len(risk_scores), 4) if risk_scores else 0.0
    risk_p95 = round(risk_scores[int(0.95 * (len(risk_scores) - 1))], 4) if risk_scores else 0.0
    model_versions = Counter(r.model_version for r in rows)
    issuer_dist = Counter((r.issuer or "").strip() for r in successful if (r.issuer or "").strip())
    extraction_completeness = [
        _extraction_completeness(r) for r in successful
    ]
    avg_extraction = round(sum(extraction_completeness) / len(extraction_completeness), 4) if extraction_completeness else 0.0

    snapshot = {
        "total_verifications": len(rows),
        "prediction_distribution": dict(prediction_dist),
        "review_status_distribution": dict(review_status_dist),
        "certificate_type_distribution": dict(cert_type_dist),
        "risk_score": {"mean": risk_mean, "p95": risk_p95},
        "model_versions": dict(model_versions),
        "issuer_distribution": dict(issuer_dist),
        "average_extraction_completeness": avg_extraction,
    }

    if args.update_baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Baseline updated: {args.baseline}")
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0

    if not args.baseline.exists():
        print(f"No baseline at {args.baseline}. Run with --update-baseline first.")
        return 1

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    base_pred = Counter(baseline.get("prediction_distribution", {}))
    base_review = Counter(baseline.get("review_status_distribution", {}))
    base_cert = Counter(baseline.get("certificate_type_distribution", {}))
    base_issuer = Counter(baseline.get("issuer_distribution", {}))
    base_risk = baseline.get("risk_score", {}) or {}

    jsd_pred = _jsd(base_pred, prediction_dist)
    jsd_review = _jsd(base_review, review_status_dist)
    jsd_cert = _jsd(base_cert, cert_type_dist)
    jsd_issuer = _jsd(base_issuer, issuer_dist)
    risk_mean_delta = abs(risk_mean - float(base_risk.get("mean", 0.0) or 0.0))
    risk_p95_delta = abs(risk_p95 - float(base_risk.get("p95", 0.0) or 0.0))

    flags = []
    if jsd_pred >= args.jsd_threshold:
        flags.append(f"prediction distribution drifted (JSD {jsd_pred:.3f} >= {args.jsd_threshold})")
    if jsd_review >= args.jsd_threshold:
        flags.append(f"review-status distribution drifted (JSD {jsd_review:.3f} >= {args.jsd_threshold})")
    if jsd_cert >= args.jsd_threshold:
        flags.append(f"certificate-type distribution drifted (JSD {jsd_cert:.3f} >= {args.jsd_threshold})")
    if jsd_issuer >= args.jsd_threshold:
        flags.append(f"issuer distribution drifted (JSD {jsd_issuer:.3f} >= {args.jsd_threshold})")
    if risk_mean_delta > 0.10:
        flags.append(f"mean risk score shifted by {risk_mean_delta:.3f} (> 0.10)")

    report = {
        "checked_at_utc": None,
        "current": snapshot,
        "baseline": baseline,
        "drift": {
            "prediction_jsd": round(jsd_pred, 4),
            "review_status_jsd": round(jsd_review, 4),
            "certificate_type_jsd": round(jsd_cert, 4),
            "issuer_jsd": round(jsd_issuer, 4),
            "risk_score_mean_delta": round(risk_mean_delta, 4),
            "risk_score_p95_delta": round(risk_p95_delta, 4),
            "threshold": args.jsd_threshold,
        },
        "drift_detected": bool(flags),
        "warnings": flags,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Report: {args.report}")
    print(f"prediction JSD={jsd_pred:.4f} review JSD={jsd_review:.4f} "
          f"cert-type JSD={jsd_cert:.4f} issuer JSD={jsd_issuer:.4f} "
          f"risk_mean_delta={risk_mean_delta:.4f} risk_p95_delta={risk_p95_delta:.4f}")
    print(f"current: {json.dumps(snapshot, sort_keys=True)}")
    if flags:
        print("DRIFT DETECTED:")
        for w in flags:
            print(f"  - {w}")
        return 1
    print("No meaningful distribution change detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
