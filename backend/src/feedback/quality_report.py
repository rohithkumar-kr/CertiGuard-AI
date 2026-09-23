"""Dataset quality report (Phase 9E).

Analyzes a reviewed candidate dataset and reports:

  - class balance
  - certificate-type balance
  - issuer diversity
  - extraction completeness
  - duplicate rate
  - missing-field rate
  - suspicious/genuine ratio
  - reviewer disagreement
  - possible data leakage (informational cross-check)

Underrepresented categories are highlighted. The data is NOT rebalanced
automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.feedback.leakage import check_split_leakage, report_duplicates

# A certificate type / issuer with fewer than this many rows is highlighted.
UNDERREPRESENTED_THRESHOLD = 5
CORE_IDENTITY_FIELDS = ("candidate_name", "organization", "course", "issue_date", "cert_id")


def _missing_field_rate(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    out = {}
    for field in CORE_IDENTITY_FIELDS:
        if field not in df.columns:
            out[field] = None
            continue
        missing = df[field].isna() | (df[field].astype(str).str.strip() == "")
        out[field] = round(float(missing.mean()), 4)
    return out


def _possible_leakage_flags(df: pd.DataFrame) -> dict:
    """Informational leakage hints. Cross-split check fails loudly; these are
    advisory flags for the report only."""
    if df.empty or "split" not in df.columns:
        return {"note": "no split column"}
    flags = {}
    for column in ("file_fingerprint", "cert_id_fingerprint", "identity_fingerprint", "certificate_id"):
        if column not in df.columns:
            continue
        train = {str(v) for v in df.loc[df["split"] == "train", column].dropna() if str(v).strip()}
        test = {str(v) for v in df.loc[df["split"] == "test", column].dropna() if str(v).strip()}
        flags[column] = int(len(train & test))
    return flags


def build_quality_report(df: pd.DataFrame, source: str = "candidate dataset") -> dict:
    if df.empty:
        return {"source": source, "n_rows": 0, "note": "empty dataset"}

    n = len(df)
    label_col = "reviewer_label" if "reviewer_label" in df.columns else "label"
    genuine = int((df[label_col] == "confirmed_genuine").sum()) if label_col == "reviewer_label" \
        else int((df[label_col] == 0).sum())
    suspicious = n - genuine

    dup_report = report_duplicates(df)
    duplicate_groups = sum(v["duplicate_groups"] for v in dup_report.values())
    duplicate_affected = sum(v["affected_rows"] for v in dup_report.values())

    cert_type_counts = df["certificate_type"].value_counts().to_dict()
    issuer_counts = df["issuer"].replace("", "unknown").value_counts().to_dict()
    completeness = df["extraction_completeness"].dropna()
    completeness_mean = round(float(completeness.mean()), 4) if len(completeness) else None
    low_completeness = int((completeness < 0.4).sum()) if len(completeness) else 0

    disagreements = int(df["is_disagreement"].sum()) if "is_disagreement" in df.columns else None

    # Underrepresented categories.
    underrepresented = {
        "certificate_types": sorted(
            t for t, c in cert_type_counts.items() if c < UNDERREPRESENTED_THRESHOLD
        ),
        "issuers": sorted(
            t for t, c in issuer_counts.items() if c < UNDERREPRESENTED_THRESHOLD
        ),
    }

    report = {
        "source": source,
        "n_rows": n,
        "class_balance": {"genuine": genuine, "suspicious": suspicious},
        "suspicious_to_genuine_ratio": round(suspicious / genuine, 4) if genuine else None,
        "certificate_type_balance": cert_type_counts,
        "issuer_diversity": len(issuer_counts),
        "issuer_counts": issuer_counts,
        "average_extraction_completeness": completeness_mean,
        "low_completeness_rows": low_completeness,
        "extraction_completeness_buckets": {
            "low (<0.4)": int((completeness < 0.4).sum()) if len(completeness) else 0,
            "medium (0.4-0.8)": int(((completeness >= 0.4) & (completeness < 0.8)).sum()) if len(completeness) else 0,
            "high (>=0.8)": int((completeness >= 0.8).sum()) if len(completeness) else 0,
        },
        "duplicate_rate": round(duplicate_affected / n, 4) if n else None,
        "duplicate_groups": duplicate_groups,
        "duplicate_affected_rows": duplicate_affected,
        "missing_field_rate": _missing_field_rate(df),
        "reviewer_disagreement_count": disagreements,
        "reviewer_disagreement_rate": round(disagreements / n, 4) if disagreements is not None and n else None,
        "possible_leakage_cross_split": _possible_leakage_flags(df),
        "underrepresented_categories": underrepresented,
        "underrepresented_threshold": UNDERREPRESENTED_THRESHOLD,
        "rebalanced": False,
        "note": "Data is not automatically rebalanced.",
    }
    return report


def load_dataset(path: Path | str) -> pd.DataFrame:
    return pd.read_csv(path)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a reviewed-dataset quality report.")
    parser.add_argument("--dataset", help="Candidate dataset CSV path")
    parser.add_argument("--output", default="monitoring/reviewed_quality_report.json",
                        help="Report JSON output path")
    args = parser.parse_args()

    if args.dataset:
        df = load_dataset(args.dataset)
        report = build_quality_report(df, source=str(args.dataset))
    else:
        # Fall back to building the dataset in-memory from the DB.
        from app.database.database import SessionLocal
        from src.feedback.candidate_dataset import collect_reviewed_rows

        db = SessionLocal()
        try:
            rows = collect_reviewed_rows(db)
        finally:
            db.close()
        df = pd.DataFrame(rows)
        report = build_quality_report(df, source="database")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()