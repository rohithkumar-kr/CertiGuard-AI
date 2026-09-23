"""Evaluate the persisted model on a held-out test split and write a report.

The report (JSON + console) includes accuracy, precision, recall, F1,
confusion matrix, and feature importances when available.
"""

import argparse
import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, f1_score, precision_score,
                             recall_score)

from src.models.train_model import split_data
from src.features.build_features import FEATURE_COLUMNS

MODEL_DIR = "./models/artifacts"
METADATA_DIR = "./models/metadata"
REPORT_DIR = "./monitoring"


def load_artifacts(model_dir=MODEL_DIR):
    model_path = os.path.join(model_dir, "model.joblib")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model artifact not found: {model_path}. Train first.")
    pipeline = joblib.load(model_path)
    with open(os.path.join(model_dir, "features.json"), "r", encoding="utf-8") as f:
        features = json.load(f)
    return pipeline, features


def main():
    parser = argparse.ArgumentParser(description="Evaluate persisted model on test split")
    parser.add_argument("--input", default=os.environ.get("DATA_PROCESSED_DIR", "./data/processed/features.csv"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    pipeline, features = load_artifacts()
    df = pd.read_csv(args.input)
    X = df[features]
    y = df["label"]

    val_size = 0.15
    test_size = 0.20
    _, _, X_test, _, _, y_test = split_data(X, y, val_size, test_size, args.seed)
    test_indices = _test_indices(df, val_size, test_size, args.seed)

    preds = pipeline.predict(X_test)
    probs = pipeline.predict_proba(X_test)[:, 1]

    model_version = "loaded_from_metadata"
    try:
        with open(os.path.join(METADATA_DIR, "model_metadata.json"), "r", encoding="utf-8") as f:
            model_version = json.load(f).get("model_version", model_version)
    except OSError:
        pass

    report = {
        "model_version": model_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_size": int(len(y_test)),
        "metrics": {
            "accuracy": round(float(accuracy_score(y_test, preds)), 4),
            "precision": round(float(precision_score(y_test, preds, zero_division=0)), 4),
            "recall": round(float(recall_score(y_test, preds, zero_division=0)), 4),
            "f1": round(float(f1_score(y_test, preds, zero_division=0)), 4),
            "confusion_matrix": confusion_matrix(y_test, preds).tolist(),
        },
    }

    if hasattr(pipeline.named_steps["model"], "feature_importances_"):
        report["feature_importances"] = dict(zip(
            features,
            [round(float(v), 4) for v in pipeline.named_steps["model"].feature_importances_],
        ))

    if "certificate_type" in df.columns:
        test_types = df["certificate_type"].iloc[test_indices]
        per_type = {}
        for cert_type in sorted(test_types.unique()):
            mask = test_types == cert_type
            if mask.sum() == 0:
                continue
            t_metrics = metrics(y_test[mask], preds[mask])
            per_type[cert_type] = t_metrics
        report["metrics_by_type"] = per_type

    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "evaluation_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Test metrics: {report['metrics']}")
    print("classification_report:\n", classification_report(y_test, preds, zero_division=0))
    if "metrics_by_type" in report:
        print("Per certificate-type metrics (test split):")
        for cert_type, m in report["metrics_by_type"].items():
            print(f"  {cert_type:12s} acc={m['accuracy']} prec={m['precision']} "
                  f"rec={m['recall']} f1={m['f1']}")
    print(f"Report written to {report_path}")


def _test_indices(df, val_size, test_size, seed):
    """Return the row indices of the test split (same split as split_data)."""
    from sklearn.model_selection import train_test_split
    _, test_idx = train_test_split(
        np.arange(len(df)), test_size=test_size, random_state=seed,
        stratify=df["label"])
    return test_idx


def metrics(y_true, y_pred):
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


if __name__ == "__main__":
    main()
