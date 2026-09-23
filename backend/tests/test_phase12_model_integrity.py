"""Phase 12 model-integrity tests (M14).

Lock the production model contract so the evidence engine can NEVER silently
change the ML layer:

  * the artifact hash is pinned (SHA-256 of model.joblib);
  * the feature schema has exactly 31 features;
  * the decision threshold stays 0.5;
  * the feature vector passed to fusion is never mutated;
  * the production model remains the single registered evidence provider;
  * fraud controls (fraud certificates stay suspicious) are never weakened;
  * no training / auto-promotion code path exists in the runtime services.
"""

import hashlib
from pathlib import Path

import pytest

from app.core.config import settings
from app.ml import model as model_service
from app.ml.model_registry import RandomForestProvider, active_provider, list_providers

EXPECTED_MODEL_SHA256 = "e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337"
EXPECTED_FEATURE_COUNT = 31
EXPECTED_THRESHOLD = 0.5


@pytest.fixture(scope="module")
def model_artifact() -> Path:
    path = settings.model_artifact_dir / "model.joblib"
    assert path.exists(), "model artifact missing"
    return path


def test_model_artifact_hash_pinned(model_artifact: Path):
    digest = hashlib.sha256(model_artifact.read_bytes()).hexdigest()
    assert digest == EXPECTED_MODEL_SHA256, (
        "Model artifact changed! If the model was deliberately retrained the "
        "SHA-256 must be updated and every contract (feature count, threshold, "
        "monitoring) re-validated."
    )


def test_feature_schema_unchanged():
    _, features, _ = model_service.load()
    assert len(features) == EXPECTED_FEATURE_COUNT
    assert len(set(features)) == EXPECTED_FEATURE_COUNT, "feature list contains duplicates"


def test_decision_threshold_unchanged():
    assert settings.decision_threshold == EXPECTED_THRESHOLD


def test_model_version_unchanged():
    assert model_service.model_version() == "random_forest_v3"


def test_fusion_never_mutates_features():
    provider = active_provider()
    assert provider is not None
    import copy

    _, features, _ = model_service.load()
    feature_dict = {name: 0 for name in features}
    snapshot = copy.deepcopy(feature_dict)
    result = provider.predict(snapshot)
    provider.to_evidence(result, snapshot)
    assert snapshot == feature_dict, "evidence provider must not mutate features"
    assert result["model_version"] == "random_forest_v3"


def test_production_model_is_single_provider():
    assert list_providers() == ["random_forest_v3"]
    assert isinstance(active_provider(), RandomForestProvider)


def test_no_auto_promotion_in_runtime_services():
    """Runtime verification services must never trigger training or promotion."""
    import inspect

    from app.services import verification_service

    src = inspect.getsource(verification_service)
    forbidden = ("fit(", ".train(", "joblib.dump", "auto_promote", "promote_model")
    for token in forbidden:
        assert token not in src, f"verification_service must not contain '{token}'"


def test_fraud_control_remains_suspicious(client):
    """A canonical fraud document still predicts suspicious at >= 0.5.

    Uses a unique synthetic document to avoid interfering with the shared
    fixtures used by other modules."""
    from tests.conftest import _make_pdf

    fraud_text = (
        "Fake Degree Store Online\n"
        "Instant Certificate\n"
        "\n"
        "Buy verified certificates online. No exam needed, instant delivery.\n"
        "Contact us on whatsapp @fraudshop for your diploma without studying.\n"
        "\n"
        "Candidate ID: FREECERT-2024-777771\n"
        "Marks: 200 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2026-12-01\n"
    )
    content = _make_pdf(fraud_text)
    resp = client.post(
        "/api/verify",
        files={"file": ("fraud_control.pdf", content, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "suspicious"
    assert body["risk_score"] >= EXPECTED_THRESHOLD


def test_prediction_interface_backward_compatible():
    """The legacy prediction result keys are still produced unchanged."""
    _, features, _ = model_service.load()
    feature_dict = {name: 0 for name in features}
    result = model_service.predict(feature_dict)
    assert {"prediction", "risk_score", "confidence", "model_version"} <= set(result)