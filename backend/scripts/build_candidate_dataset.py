"""Phase 9D: candidate training dataset builder from reviewed feedback.

Qualifying rows (confirmed_genuine / confirmed_suspicious) are converted into
a candidate dataset with a leakage-safe train/test split. Uncertain and
not_reviewed rows are excluded. Output is a CSV + report, NOT a model.

Usage:
    python scripts/build_candidate_dataset.py \
        [--output-dir data/reviewed] \
        [--test-fraction 0.20] \
        [--seed 42] \
        [--external-dir external_validation]
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.database.database import SessionLocal  # noqa: E402
from src.feedback.candidate_dataset import build_candidate_dataset  # noqa: E402
from src.feedback.labels import CANDIDATE_DATA_DIR, DEFAULT_TEST_FRACTION  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    output_dir = ROOT / CANDIDATE_DATA_DIR
    test_fraction = DEFAULT_TEST_FRACTION
    seed = 42
    external_dir = ROOT / "external_validation"

    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--output-dir="):
            output_dir = ROOT / arg.split("=", 1)[1]
        elif arg.startswith("--test-fraction="):
            test_fraction = float(arg.split("=", 1)[1])
        elif arg.startswith("--seed="):
            seed = int(arg.split("=", 1)[1])
        elif arg == "--no-external-check":
            external_dir = None

    db = SessionLocal()
    try:
        report = build_candidate_dataset(
            db, output_dir, test_fraction=test_fraction, seed=seed,
            external_dir=external_dir,
        )
    finally:
        db.close()

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()