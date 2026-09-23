"""Tests for the ML model artifact and prediction behavior.

These tests do NOT retrain the model; they exercise the persisted artifacts.
"""

import json

import pytest

from app.core.config import settings
from app.ml import model as model_service
from src.features.build_features import FEATURE_COLUMNS


def _genuine_features() -> dict:
    return {
        "cert_id_format_valid": 1,
        "cert_id_checksum_valid": 1,
        "issuer_known": 1,
        "issue_year_valid": 1,
        "date_consistency_valid": 1,
        "candidate_name_present": 1,
        "course_present": 1,
        "organization_present": 1,
        "text_field_completeness": 1.0,
        "marks_pattern_valid": 1,
        "grade_consistency_valid": 1,
        "suspicious_keyword_count": 0,
        "suspicious_url_present": 0,
        "signature_present": 1,
        "seal_present": 1,
        "qr_present": 1,
        "visual_blank_ratio": 0.05,
        "visual_sharpness": 0.85,
        "visual_noise": 0.05,
        "visual_color_anomaly": 0,
        "text_duplicate_similarity": 0.0,
        "issuer_domain_trust": 1.0,
        # --- v2 generalized features ---
        "certificate_type_academic": 1,
        "certificate_type_completion": 0,
        "certificate_type_training": 0,
        "certificate_type_technical": 0,
        "recipient_present": 1,
        "completion_date_present": 1,
        "issuer_present": 1,
        "completion_title_present": 1,
        "certificate_structure_completeness": 1.0,
    }


def _suspicious_features() -> dict:
    feats = _genuine_features()
    feats.update({
        "cert_id_format_valid": 0,
        "cert_id_checksum_valid": 0,
        "issuer_known": 0,
        "marks_pattern_valid": 0,
        "grade_consistency_valid": 0,
        "suspicious_keyword_count": 4,
        "suspicious_url_present": 1,
        "signature_present": 0,
        "seal_present": 0,
        "qr_present": 0,
        "visual_blank_ratio": 0.9,
        "visual_sharpness": 0.15,
        "visual_noise": 0.5,
        "visual_color_anomaly": 1,
        "issuer_domain_trust": 0.0,
        "certificate_type_academic": 0,
        "certificate_type_completion": 0,
        "certificate_type_training": 0,
        "certificate_type_technical": 0,
        "recipient_present": 0,
        "completion_date_present": 0,
        "issuer_present": 0,
        "completion_title_present": 0,
        "certificate_structure_completeness": 0.0,
    })
    return feats


def test_model_artifact_exists():
    assert (settings.model_artifact_dir / "model.joblib").exists()
    assert (settings.model_artifact_dir / "features.json").exists()


def test_model_loads():
    pipeline, features, metadata = model_service.load()
    assert pipeline is not None
    assert metadata is not None
    assert metadata["model_version"] == settings.model_version


def test_feature_metadata_matches_training_schema():
    _, features, _ = model_service.load()
    assert features == FEATURE_COLUMNS
    assert len(features) == 31


def test_model_info_endpoint_shape(client):
    resp = client.get("/api/model/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_version"] == settings.model_version
    assert body["features"] == FEATURE_COLUMNS
    assert "metrics" in body


def test_prediction_returns_expected_fields():
    result = model_service.predict(_genuine_features())
    assert set(result.keys()) == {"prediction", "risk_score", "confidence", "model_version"}
    assert result["model_version"] == settings.model_version


def test_probability_and_confidence_in_range():
    for feats in (_genuine_features(), _suspicious_features()):
        result = model_service.predict(feats)
        assert 0.0 <= result["risk_score"] <= 1.0
        assert 0.0 <= result["confidence"] <= 1.0
        assert result["prediction"] in {"genuine", "suspicious"}


def test_genuine_features_predict_genuine():
    result = model_service.predict(_genuine_features())
    assert result["prediction"] == "genuine"
    assert result["risk_score"] < 0.5


def test_suspicious_features_predict_suspicious():
    result = model_service.predict(_suspicious_features())
    assert result["prediction"] == "suspicious"
    assert result["risk_score"] >= 0.5


def test_invalid_feature_input_uses_defaults():
    # Missing/extra/None values must not crash prediction.
    result = model_service.predict({})
    assert result["prediction"] in {"genuine", "suspicious"}
    assert 0.0 <= result["risk_score"] <= 1.0

    noisy = _genuine_features()
    noisy["visual_blank_ratio"] = "not-a-number"  # non-numeric is coerced to 0.0
    noisy["unknown_key"] = 123
    result2 = model_service.predict(noisy)
    assert result2["prediction"] in {"genuine", "suspicious"}


def test_prediction_is_deterministic():
    r1 = model_service.predict(_genuine_features())
    r2 = model_service.predict(_genuine_features())
    assert r1 == r2


def test_active_model_is_v3():
    _, _, metadata = model_service.load()
    assert metadata["model_version"] == "random_forest_v3"
    assert metadata["feature_schema_version"] == "v3"
    assert metadata["dataset_version"] == "v3"


def test_v3_artifact_exists():
    assert (settings.model_artifact_dir / "random_forest_v3" / "model.joblib").exists()
    assert (settings.model_artifact_dir / "random_forest_v3" / "features.json").exists()
    assert (settings.model_metadata_dir / "random_forest_v3" / "model_metadata.json").exists()


def test_v3_model_loads_with_technical_feature():
    pipeline, features, metadata = model_service.load()
    assert "certificate_type_technical" in features
    assert len(features) == 31


def test_technical_genuine_features_predict_genuine():
    feats = _genuine_features()
    feats.update({
        "cert_id_format_valid": 0,
        "cert_id_checksum_valid": 0,
        "certificate_type_academic": 0,
        "certificate_type_completion": 0,
        "certificate_type_training": 0,
        "certificate_type_technical": 1,
        "issuer_known": 1,
        "issuer_domain_trust": 1.0,
        "marks_pattern_valid": 0,
        "grade_consistency_valid": 0,
        "signature_present": 0,
        "seal_present": 0,
        "qr_present": 0,
    })
    result = model_service.predict(feats)
    assert result["prediction"] == "genuine"
    assert result["risk_score"] < 0.5


def test_technical_suspicious_features_predict_suspicious():
    feats = _suspicious_features()
    feats.update({
        "certificate_type_technical": 1,
        "suspicious_keyword_count": 3,
        "suspicious_url_present": 1,
    })
    result = model_service.predict(feats)
    assert result["prediction"] == "suspicious"
    assert result["risk_score"] >= 0.5