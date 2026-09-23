"""Phase 9E: dataset quality report for reviewed feedback / candidate dataset.

Reports class balance, certificate-type balance, issuer diversity, extraction
completeness, duplicate rate, missing-field rate, suspicious/genuine ratio,
reviewer disagreement and possible leakage. Underrepresented categories are
highlighted. Data is never rebalanced automatically.

Usage:
    python scripts/data_quality_report.py [--dataset data/reviewed/<batch>.csv]
                                          [--output monitoring/reviewed_quality_report.json]
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.feedback.quality_report import (  # noqa: E402
    build_quality_report, load_dataset, main as _main,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    args = sys.argv[1:]
    dataset = None
    output = ROOT / "monitoring" / "reviewed_quality_report.json"
    for arg in args:
        if arg.startswith("--dataset="):
            dataset = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            output = ROOT / arg.split("=", 1)[1]

    if dataset:
        df = load_dataset(dataset)
        report = build_quality_report(df, source=dataset)
    else:
        from app.database.database import SessionLocal  # noqa: F401
        from src.feedback.candidate_dataset import collect_reviewed_rows  # noqa: E402
        import pandas as pd  # noqa: E402

        db = SessionLocal()
        try:
            rows = collect_reviewed_rows(db)
        finally:
            db.close()
        df = pd.DataFrame(rows)
        report = build_quality_report(df, source="database")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nReport written to {output}")


if __name__ == "__main__":
    main()