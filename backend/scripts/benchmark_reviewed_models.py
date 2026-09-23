"""Phase 9J: benchmark candidate models on an approved reviewed dataset.

Benchmarks random_forest_v3, random_forest_candidate, XGBoost and Logistic
Regression on the approved reviewed dataset (leakage-checked). Reports the
standard metrics plus per-certificate-type performance and a ranking by the
decision priority. NEVER promotes a model.

Usage:
    python scripts/benchmark_reviewed_models.py \
        --dataset data/reviewed/<batch>.csv \
        [--output monitoring/reviewed_benchmark_report.json] \
        [--seed 42]
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.feedback.benchmark import benchmark_reviewed_dataset  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    dataset = None
    output = ROOT / "monitoring" / "reviewed_benchmark_report.json"
    seed = 42
    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--dataset="):
            dataset = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            output = ROOT / arg.split("=", 1)[1]
        elif arg.startswith("--seed="):
            seed = int(arg.split("=", 1)[1])

    if not dataset:
        print("--dataset=<path> is required. Run build_candidate_dataset.py first.")
        sys.exit(2)

    report = benchmark_reviewed_dataset(dataset, output, seed=seed)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()