"""Phase 9C: model error analysis over reviewed certificates.

Reads reviewer feedback from the database and compares AI predictions to
human-review decisions (ground truth). Metrics with too few samples are
reported as "insufficient samples".

Usage:
    python scripts/analyze_feedback.py [--output monitoring/reviewed_error_analysis.json]
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.database.database import SessionLocal  # noqa: E402
from src.feedback.analyze import analyze_feedback, format_analysis  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    output = ROOT / "monitoring" / "reviewed_error_analysis.json"
    if len(sys.argv) > 1 and sys.argv[1].startswith("--output="):
        output = ROOT / sys.argv[1].split("=", 1)[1]

    db = SessionLocal()
    try:
        report = analyze_feedback(db)
    finally:
        db.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(format_analysis(report))
    print(f"\nReport written to {output}")


if __name__ == "__main__":
    main()