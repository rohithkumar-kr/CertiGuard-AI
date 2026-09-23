"""Inference helpers: load persisted artifacts and predict a single record.

The feature dictionary must contain the same keys as the training features.
A zero-fill fallback is provided so missing keys do not crash inference.
"""

import json
import os

import joblib
import pandas as pd

from src.features.build_features import FEATURE_COLUMNS

MODEL_DIR = "./models/artifacts"


def load_model(model_dir=MODEL_DIR):
    model_path = os.path.join(model_dir, "model.joblib")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model artifact not found: {model_path}. Run the training pipeline first.")
    pipeline = joblib.load(model_path)
    with open(os.path.join(model_dir, "features.json"), "r", encoding="utf-8") as f:
        features = json.load(f)
    return pipeline, features


def _coerce(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_vector(features: dict, feature_columns=None):
    columns = feature_columns or FEATURE_COLUMNS
    row = {col: _coerce(features.get(col)) for col in columns}
    return pd.DataFrame([row])


def predict(features: dict, model_dir=MODEL_DIR, threshold: float = 0.5):
    """Return prediction dict: prediction, risk_score, confidence.

    ``threshold`` is the decision boundary on the predicted fraud probability.
    The default (0.5) is the validated production threshold; it must not be
    lowered without re-validating generalization metrics.
    """
    pipeline, columns = load_model(model_dir)
    vector = build_vector(features, columns)
    prob_fraud = float(pipeline.predict_proba(vector)[0, 1])
    risk_score = round(prob_fraud, 4)
    confidence = round(max(prob_fraud, 1 - prob_fraud), 4)
    prediction = "suspicious" if prob_fraud >= threshold else "genuine"
    return {
        "prediction": prediction,
        "risk_score": risk_score,
        "confidence": confidence,
    }
