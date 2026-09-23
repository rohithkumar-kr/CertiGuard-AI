"""BENCHMARK ONLY: compare candidate classifiers on the current v2 pipeline.

Reads the processed feature set (data/processed/features.csv), splits it with
the SAME stratified train/val/test split and seed used by src/models/train_model.py
(test=0.20, val=0.15, seed=42), trains LogisticRegression / RandomForest /
XGBoost with reproducible configurations, and reports validation + held-out
test metrics plus external-document predictions.

This script NEVER writes to models/artifacts or models/metadata: the production
model (active model.joblib) is left untouched. Results go to
monitoring/benchmark_report.json only.
"""

import json
import os
import pathlib
import sys

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score,
                             confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from src.features.build_features import FEATURE_COLUMNS  # noqa: E402

REPORT_PATH = BACKEND / "monitoring" / "benchmark_report.json"

EXTERNAL_DOCS = [
    ("aws_completion_certificate", BACKEND / "uploads" / "52e3ce2100a04b8a8324e14d0f83a416.pdf"),
    ("genuine_certificate", BACKEND / "samples" / "genuine_certificate.pdf"),
    ("inconsistent_certificate", BACKEND / "samples" / "inconsistent_certificate.pdf"),
]


def load_config():
    with open(BACKEND / "configs" / "settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_data(X, y, val_size, test_size, seed):
    X_rest, X_test, y_rest, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y)
    val_frac = val_size / (1 - test_size)
    X_train, X_val, y_train, y_val = train_test_split(
        X_rest, y_rest, test_size=val_frac, random_state=seed, stratify=y_rest)
    return X_train, X_val, X_test, y_train, y_val, y_test


def candidate_pipelines(seed, train_y):
    n_neg = int((train_y == 0).sum())
    n_pos = int((train_y == 1).sum())
    return {
        "logistic_regression": Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=2000, random_state=seed, class_weight="balanced")),
        ]),
        "random_forest": Pipeline([
            ("scaler", StandardScaler()),
            ("model", RandomForestClassifier(
                n_estimators=300, max_depth=12, random_state=seed, class_weight="balanced")),
        ]),
        "xgboost": Pipeline([
            ("scaler", StandardScaler()),
            ("model", XGBClassifier(
                n_estimators=300, max_depth=6, learning_rate=0.1,
                subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
                scale_pos_weight=n_neg / n_pos,
                eval_metric="logloss", random_state=seed,
                tree_method="hist")),
        ]),
    }


def full_metrics(y_true, y_pred, y_proba):
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "roc_auc": round(float(roc_auc_score(y_true, y_proba)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_proba)), 4),
    }


def external_features(doc_path):
    from app.services.extraction_service import extract_document
    from app.services.feature_service import build_features_from_extraction
    from app.utils.file_utils import validate_file

    content = doc_path.read_bytes()
    ext = validate_file(doc_path.name, content)
    extraction = extract_document(str(doc_path), ext)
    return build_features_from_extraction(extraction), extraction


def predict_external(pipeline, features_dict):
    row = {c: float(features_dict.get(c, 0.0) or 0.0) for c in FEATURE_COLUMNS}
    vector = pd.DataFrame([row])
    prob_fraud = float(pipeline.predict_proba(vector)[0, 1])
    return {
        "prediction": "suspicious" if prob_fraud >= 0.5 else "genuine",
        "risk_score": round(prob_fraud, 4),
        "confidence": round(max(prob_fraud, 1 - prob_fraud), 4),
    }


def main():
    cfg = load_config()
    seed = cfg["pipeline"].get("seed", 42)
    test_size = cfg["pipeline"].get("test_size", 0.20)
    val_size = cfg["pipeline"].get("validation_size", 0.15)

    df = pd.read_csv(BACKEND / "data" / "processed" / "features.csv")
    X = df[FEATURE_COLUMNS]
    y = df["label"]

    X_train, X_val, X_test, y_train, y_val, y_test = split_data(
        X, y, val_size, test_size, seed)
    print(f"Split (seed={seed}): train={len(X_train)} val={len(X_val)} test={len(X_test)}")

    candidates = candidate_pipelines(seed, y_train)
    val_results, test_results, externals = {}, {}, {}

    for name, pipe in candidates.items():
        pipe.fit(X_train, y_train)
        val_proba = pipe.predict_proba(X_val)[:, 1]
        test_proba = pipe.predict_proba(X_test)[:, 1]
        val_results[name] = full_metrics(y_val, pipe.predict(X_val), val_proba)
        test_results[name] = full_metrics(y_test, pipe.predict(X_test), test_proba)

        externals[name] = {}
        for doc_name, doc_path in EXTERNAL_DOCS:
            feats, _ = external_features(doc_path)
            externals[name][doc_name] = predict_external(pipe, feats)

    report = {
        "benchmark": "random_forest_vs_xgboost",
        "pipeline": {
            "feature_schema": "v2",
            "feature_count": len(FEATURE_COLUMNS),
            "dataset_rows": int(len(df)),
            "seed": seed,
            "test_size": test_size,
            "validation_size": val_size,
            "splits": {"train": len(X_train), "val": len(X_val), "test": len(X_test)},
        },
        "validation": val_results,
        "test": test_results,
        "external_documents": externals,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    header = f"{'Model':<22}{'Acc':>8}{'Prec':>8}{'Recall':>8}{'F1':>8}{'ROC-AUC':>9}{'PR-AUC':>9}"
    print("\n--- VALIDATION (seed 42 split) ---")
    print(header)
    for name, m in val_results.items():
        print(f"{name:<22}{m['accuracy']:>8}{m['precision']:>8}{m['recall']:>8}{m['f1']:>8}{m['roc_auc']:>9}{m['pr_auc']:>9}")
    print("\n--- HELD-OUT TEST ---")
    print(header)
    for name, m in test_results.items():
        print(f"{name:<22}{m['accuracy']:>8}{m['precision']:>8}{m['recall']:>8}{m['f1']:>8}{m['roc_auc']:>9}{m['pr_auc']:>9}")
    print("\n--- CONFUSION MATRICES (test, [[TN, FP], [FN, TP]]) ---")
    for name, m in test_results.items():
        print(f"{name:<22} {m['confusion_matrix']}")

    print("\n--- EXTERNAL DOCUMENTS (not in training/test) ---")
    for name, docs in externals.items():
        for doc_name, r in docs.items():
            print(f"{name:<22} {doc_name:<28} {r['prediction']:<10} risk={r['risk_score']} conf={r['confidence']}")

    # Selection priority: fraud recall, fraud F1, precision, overall F1, accuracy.
    print("\n--- SELECTION (validation, priority: recall -> F1 -> precision -> F1 -> accuracy) ---")
    ranked = sorted(
        val_results.items(),
        key=lambda kv: (kv[1]["recall"], kv[1]["f1"], kv[1]["precision"], kv[1]["accuracy"]),
        reverse=True,
    )
    for i, (name, m) in enumerate(ranked, 1):
        print(f"{i}. {name}  recall={m['recall']} f1={m['f1']} precision={m['precision']} acc={m['accuracy']}")
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()