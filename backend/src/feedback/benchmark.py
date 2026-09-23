"""Future model benchmark pipeline (Phase 9J).

Benchmarks candidate classifiers on the APPROVED reviewed dataset only:

  - random_forest_v3      (same configuration as the current production model)
  - random_forest_candidate
  - xgboost
  - logistic_regression

Metrics: accuracy, precision, recall, F1, ROC-AUC, PR-AUC, false-positive rate,
false-negative rate, plus performance by certificate type.

Selection priority (validation): suspicious recall -> suspicious F1 ->
precision -> overall F1 -> accuracy.

This tool NEVER promotes a model: it writes a report only and leaves
models/artifacts and models/metadata untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core.logging import get_logger
from src.features.build_features import FEATURE_COLUMNS
from src.feedback.leakage import check_split_leakage
from src.feedback.labels import MIN_GROUP_SAMPLES

logger = get_logger("reviewed_benchmark")

INSUFFICIENT = "insufficient samples"

# (model_name, display_name)
CANDIDATES = {
    "random_forest_v3": ("random_forest_v3", {
        "n_estimators": 300, "max_depth": 12, "class_weight": "balanced",
    }),
    "random_forest_candidate": ("random_forest_candidate", {
        "n_estimators": 500, "max_depth": None, "class_weight": "balanced",
        "min_samples_leaf": 2,
    }),
    "xgboost": ("xgboost", {}),
    "logistic_regression": ("logistic_regression", {}),
}


def _make_pipeline(name: str, params: dict, seed: int, y_train: np.ndarray):
    if name == "xgboost":
        from xgboost import XGBClassifier
        n_neg = int((y_train == 0).sum())
        n_pos = int((y_train == 1).sum())
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", XGBClassifier(
                n_estimators=300, max_depth=6, learning_rate=0.1,
                subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                scale_pos_weight=n_neg / max(n_pos, 1),
                eval_metric="logloss", random_state=seed, tree_method="hist")),
        ])
    if name == "logistic_regression":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, random_state=seed, class_weight="balanced")),
        ])
    if name == "random_forest_v3":
        return Pipeline([
            ("scaler", StandardScaler()),
            ("model", RandomForestClassifier(
                n_estimators=params["n_estimators"], max_depth=params["max_depth"],
                random_state=seed, class_weight=params["class_weight"])),
        ])
    return Pipeline([
        ("scaler", StandardScaler()),
        ("model", RandomForestClassifier(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            min_samples_leaf=params.get("min_samples_leaf", 1),
            random_state=seed, class_weight=params["class_weight"])),
    ])


def _safe(value):
    return round(float(value), 4)


def _full_metrics(y_true, y_pred, y_proba):
    n = len(y_true)
    if n < MIN_GROUP_SAMPLES:
        return {"n": n, "sufficient": False, "note": INSUFFICIENT}
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    return {
        "n": n,
        "sufficient": True,
        "accuracy": _safe(accuracy_score(y_true, y_pred)),
        "precision": _safe(precision_score(y_true, y_pred, zero_division=0)),
        "recall": _safe(recall_score(y_true, y_pred, zero_division=0)),
        "f1": _safe(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": _safe(roc_auc_score(y_true, y_proba)) if len(np.unique(y_true)) > 1 else None,
        "pr_auc": _safe(average_precision_score(y_true, y_proba)),
        "false_positive_rate": _safe(fp / (fp + int((y_true == 0).sum()))) if (fp + int((y_true == 0).sum())) else 0.0,
        "false_negative_rate": _safe(fn / (fn + int((y_true == 1).sum()))) if (fn + int((y_true == 1).sum())) else 0.0,
        "confusion_matrix": {
            "tn": int(((y_pred == 0) & (y_true == 0)).sum()),
            "fp": fp,
            "fn": fn,
            "tp": int(((y_pred == 1) & (y_true == 1)).sum()),
        },
    }


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows with a usable feature vector and a valid label."""
    if df.empty:
        return df
    usable = df.copy()
    if "features_available" in usable.columns:
        usable = usable[usable["features_available"] == True]  # noqa: E712
    usable = usable.dropna(subset=FEATURE_COLUMNS + ["label"])
    return usable


def _per_certificate_type(pipe, df: pd.DataFrame) -> dict:
    out = {}
    for cert_type, group in df.groupby("certificate_type"):
        X = group[FEATURE_COLUMNS]
        y = group["label"].astype(int).values
        if len(group) < MIN_GROUP_SAMPLES or len(set(y)) < 2:
            out[str(cert_type)] = {"n": int(len(group)), "sufficient": False, "note": INSUFFICIENT}
            continue
        proba = pipe.predict_proba(X)[:, 1]
        pred = (proba >= 0.5).astype(int)
        out[str(cert_type)] = _full_metrics(y, pred, proba)
    return out


def benchmark_reviewed_dataset(
    dataset_path: Path | str,
    output_report: Path | str = "monitoring/reviewed_benchmark_report.json",
    seed: int = 42,
) -> dict:
    """Run the benchmark on an approved reviewed dataset.

    Uses the stored 'split' column for train/test (already leakage-checked).
    Raises LeakageError if the dataset fails the split-leakage check.
    """
    df = pd.read_csv(dataset_path)
    check_split_leakage(df)
    df = prepare_dataset(df)

    report = {
        "dataset": str(dataset_path),
        "benchmark_note": "Candidate benchmarking on approved reviewed data. "
                          "Nothing is promoted.",
        "seed": seed,
        "rows_usable": int(len(df)),
        "models": {},
        "selection_priority": [
            "suspicious recall", "suspicious f1", "precision", "overall f1", "accuracy",
        ],
    }

    if "split" not in df.columns or not {"train", "test"}.issubset(set(df["split"].dropna())):
        report["rows_usable"] = int(len(df))
        report["error"] = "Dataset needs both train and test splits."
        return report

    train = df[df["split"] == "train"]
    test = df[df["split"] == "test"]
    X_train = train[FEATURE_COLUMNS].astype(float)
    y_train = train["label"].astype(int).values
    X_test = test[FEATURE_COLUMNS].astype(float)
    y_test = test["label"].astype(int).values

    report["splits"] = {"train": int(len(train)), "test": int(len(test))}

    if len(X_train) < 10 or len(X_test) < 10:
        report["error"] = "Too few train/test rows to benchmark reliably."
        return report

    validation_results: dict[str, dict] = {}
    for name, (display, params) in CANDIDATES.items():
        pipe = _make_pipeline(name, params, seed, y_train)
        pipe.fit(X_train, y_train)
        test_proba = pipe.predict_proba(X_test)[:, 1]
        test_pred = (test_proba >= 0.5).astype(int)
        results = _full_metrics(y_test, test_pred, test_proba)
        results["by_certificate_type"] = _per_certificate_type(pipe, test)
        report["models"][display] = results
        validation_results[display] = results

    ranked = sorted(
        validation_results.items(),
        key=lambda kv: (
            kv[1].get("recall", 0.0) if kv[1].get("sufficient") else -1,
            kv[1].get("f1", 0.0) if kv[1].get("sufficient") else -1,
            kv[1].get("precision", 0.0) if kv[1].get("sufficient") else -1,
            kv[1].get("accuracy", 0.0) if kv[1].get("sufficient") else -1,
        ),
        reverse=True,
    )
    report["ranking"] = [
        {
            "rank": i + 1,
            "model": name,
            "suspicious_recall": m.get("recall"),
            "suspicious_f1": m.get("f1"),
            "precision": m.get("precision"),
            "accuracy": m.get("accuracy"),
        }
        for i, (name, m) in enumerate(ranked)
    ]
    report["promoted"] = False
    report["promotion_decision"] = (
        "No model is promoted automatically. A promotion requires an explicit "
        "decision after benchmark + frozen external validation review."
    )

    out = Path(output_report)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Reviewed benchmark written to %s", out)
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark candidate models on an approved reviewed dataset."
    )
    parser.add_argument("--dataset", required=True, help="Candidate dataset CSV path")
    parser.add_argument("--output", default="monitoring/reviewed_benchmark_report.json")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = benchmark_reviewed_dataset(args.dataset, args.output, seed=args.seed)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()