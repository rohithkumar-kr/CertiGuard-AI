"""End-to-end ML pipeline: generate data -> build features -> train -> evaluate.

Usage (from backend/):
    python -m src.training.run_pipeline
"""

import subprocess
import sys
import os


def run(module: str) -> None:
    print(f"\n=== {module} ===")
    code = subprocess.run([sys.executable, "-m", module], cwd=os.getcwd()).returncode
    if code != 0:
        raise SystemExit(f"Step failed: {module} (exit {code})")


def main():
    run("src.data.make_dataset")
    run("src.features.build_features")
    run("src.models.train_model")
    run("src.models.evaluate_model")
    print("\nPipeline complete. Artifacts in models/, reports in monitoring/.")


if __name__ == "__main__":
    main()
