"""Train candidate fraud-risk classifiers, select the best on a validation
split, and persist versioned artifacts.

Pipeline: processed features -> stratified train/val/test -> standardize ->
fit candidate models -> evaluate on validation -> persist best model,
preprocessor, feature list and versioned metadata.
"""

import argparse
import json
import os
import tempfile
import shutil
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV

from src.features.build_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION
from src.data.make_dataset import DATASET_VERSION
from src.training import experiment_tracker

MODEL_DIR = "./models/artifacts"
METADATA_DIR = "./models/metadata"
DEFAULT_VERSION = "random_forest_v3"


def _dump_model_and_features(pipeline, features, version, timestamp, promote=True):
    """Persist artifacts into the versioned dir (and optionally the active
    flat paths).

    The active flat paths (models/artifacts/model.joblib, features.json and
    models/metadata/model_metadata.json) are what the backend loads. By
    default (promote=True) the current model becomes the active one while the
    versioned copy stays for rollback. Candidate training uses promote=False
    so a new version is stored under its own versioned dir WITHOUT changing
    the active production model.
    """
    os.makedirs(MODEL_DIR, exist_ok=True)
    os.makedirs(METADATA_DIR, exist_ok=True)
    versioned_artifacts = os.path.join(MODEL_DIR, version)
    versioned_metadata = os.path.join(METADATA_DIR, version)
    os.makedirs(versioned_artifacts, exist_ok=True)
    os.makedirs(versioned_metadata, exist_ok=True)

    targets = {os.path.join(versioned_artifacts, "model.joblib"): pipeline}
    if promote:
        targets[os.path.join(MODEL_DIR, "model.joblib")] = pipeline
    for path, obj in targets.items():
        joblib.dump(obj, path)

    features_payload = json.dumps(features, indent=2)
    paths = [os.path.join(versioned_artifacts, "features.json")]
    if promote:
        paths.append(os.path.join(MODEL_DIR, "features.json"))
    for path in paths:
        with open(path, "w", encoding="utf-8") as f:
            f.write(features_payload)
    return versioned_artifacts, versioned_metadata


def load_config():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "settings.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def candidate_pipelines(seed):
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
    }


def split_data(X, y, val_size, test_size, seed):
    X_rest, X_test, y_rest, y_test = train_test_split(
        X, y, test_size=test_size, random_state=seed, stratify=y)
    if val_size > 0:
        val_frac = val_size / (1 - test_size)
        X_train, X_val, y_train, y_val = train_test_split(
            X_rest, y_rest, test_size=val_frac, random_state=seed, stratify=y_rest)
    else:
        X_train, X_val, y_train, y_val = X_rest, None, y_rest, None
    return X_train, X_val, X_test, y_train, y_val, y_test


def metrics(y_true, y_pred):
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def persist_artifacts(best_pipeline, best_name, features, train_metrics, val_metrics,
                      test_metrics, params, seed, split_sizes, version=DEFAULT_VERSION,
                      promote=True):
    timestamp = datetime.now(timezone.utc).isoformat()
    versioned_artifacts, versioned_metadata = _dump_model_and_features(
        best_pipeline, features, version, timestamp, promote=promote)

    metadata = {
        "model_version": version,
        "model_name": best_name,
        "created_at": timestamp,
        "seed": seed,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "split_sizes": {
            "train": split_sizes["train"],
            "validation": split_sizes["validation"],
            "test": split_sizes["test"],
        },
        "features": features,
        "params": params,
        "metrics": {
            "train": train_metrics,
            "validation": val_metrics,
            "test": test_metrics,
        },
        "promoted": bool(promote),
        "artifacts": {
            "model": os.path.join(MODEL_DIR, version, "model.joblib"),
            "features": os.path.join(MODEL_DIR, version, "features.json"),
            "active_model": os.path.join(MODEL_DIR, "model.joblib") if promote else None,
        },
    }
    meta_paths = [os.path.join(versioned_metadata, "model_metadata.json")]
    if promote:
        meta_paths.append(os.path.join(METADATA_DIR, "model_metadata.json"))
    for path in meta_paths:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    experiment_tracker.log_run(
        model_name=best_name,
        params={**params, "seed": seed, "feature_count": len(features)},
        metrics={"validation": val_metrics, "test": test_metrics},
        artifacts_dir=versioned_artifacts,
        model_version=version,
        extra={"features": features, "dataset_version": DATASET_VERSION,
               "feature_schema_version": FEATURE_SCHEMA_VERSION},
    )
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Train fraud-risk classifiers")
    parser.add_argument("--input", default=os.environ.get("DATA_PROCESSED_DIR", "./data/processed/features.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--version", default=os.environ.get("MODEL_VERSION", DEFAULT_VERSION))
    parser.add_argument("--no-promote", action="store_true",
                        help="Save the candidate to its versioned dir without changing the active model")
    parser.add_argument("--calibrate", default=None, choices=["sigmoid", "isotonic"],
                        help="Wrap the selected model in CalibratedClassifierCV (probabilities become "
                             "calibrated; calibration is fit inside cross-validation on the training "
                             "split only). Default: raw classifier probabilities (no calibration).")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    X = df[FEATURE_COLUMNS]
    y = df["label"]

    cfg = load_config()
    val_size = cfg["pipeline"].get("validation_size", 0.15)
    test_size = cfg["pipeline"].get("test_size", 0.20)

    X_train, X_val, X_test, y_train, y_val, y_test = split_data(
        X, y, val_size, test_size, args.seed)
    split_sizes = {
        "train": int(len(X_train)),
        "validation": int(len(X_val)),
        "test": int(len(X_test)),
    }
    print(f"train={len(X_train)} val={len(X_val)} test={len(X_test)}")

    candidates = candidate_pipelines(args.seed)
    results = {}
    best_name, best_f1 = None, -1.0
    for name, pipe in candidates.items():
        pipe.fit(X_train, y_train)
        val_pred = pipe.predict(X_val)
        m = metrics(y_val, val_pred)
        results[name] = m
        print(f"{name}: val F1={m['f1']} precision={m['precision']} recall={m['recall']}")
        if m["f1"] > best_f1:
            best_f1, best_name = m["f1"], name

    if best_name is None:
        raise RuntimeError("No candidate model trained")

    best_pipe = candidates[best_name]
    val_metrics_selected = results[best_name]
    if args.calibrate:
        print(f"Applying {args.calibrate} calibration (fit on training split via CV)")
        best_pipe = CalibratedClassifierCV(best_pipe, method=args.calibrate, cv=3)
        best_pipe.fit(X_train, y_train)
        best_name = f"{best_name}_calibrated_{args.calibrate}"
        val_metrics_selected = metrics(y_val, best_pipe.predict(X_val))
    train_metrics = metrics(y_train, best_pipe.predict(X_train))
    test_metrics = metrics(y_test, best_pipe.predict(X_test))
    print(f"Selected {best_name} | test metrics: {test_metrics}")

    cfg_models = cfg.get("models", {}).get("candidates", [])
    params = {}
    for c in cfg_models:
        if c.get("name") == "random_forest":
            params = {k: v for k, v in c.get("params", {}).items() if k != "random_state"}
    params["class_weight"] = "balanced"
    if args.calibrate:
        params["calibration"] = args.calibrate

    metadata = persist_artifacts(best_pipe, best_name, FEATURE_COLUMNS,
                                 train_metrics, val_metrics_selected, test_metrics,
                                 params, args.seed, split_sizes, version=args.version,
                                 promote=not args.no_promote)
    print(f"Saved model version={metadata['model_version']} -> {MODEL_DIR}"
          + (" (candidate only)" if args.no_promote else " (promoted to active)"))


if __name__ == "__main__":
    main()
