"""Model registry (Phase 12, M8).

Turns ML models into *evidence providers* so the fusion layer can treat them
like any other evidence source. The production model (`random_forest_v3`) is
registered under the exact same loader used by the rest of the application —
no retraining, no feature changes, no threshold changes. It remains one
provider among many.
"""

from __future__ import annotations

from app.ml import model as model_service


class ModelEvidenceProvider:
    provider_id = "base"

    def predict(self, features: dict) -> dict:  # noqa: ANN001
        raise NotImplementedError

    def to_evidence(self, result: dict, features: dict) -> dict:  # noqa: ANN001
        """Convert a prediction result into an evidence dict for the fusion
        layer. Providers must NOT mutate the feature vector."""
        raise NotImplementedError


class RandomForestProvider(ModelEvidenceProvider):
    """Wraps the production random-forest model as an evidence provider."""

    provider_id = "random_forest_v3"

    def predict(self, features: dict) -> dict:
        return model_service.predict(dict(features))  # defensive copy

    def to_evidence(self, result: dict, features: dict) -> dict:  # noqa: ANN001
        return {
            "provider": self.provider_id,
            "prediction": result["prediction"],
            "risk_score": result["risk_score"],
            "confidence": result["confidence"],
            "model_version": result["model_version"],
            "feature_count": len(features),
        }


_registry: dict[str, ModelEvidenceProvider] = {}


def register(provider: ModelEvidenceProvider) -> None:
    _registry[provider.provider_id] = provider


def get_provider(provider_id: str | None = None) -> ModelEvidenceProvider | None:
    if provider_id:
        return _registry.get(provider_id)
    return _registry.get(RandomForestProvider.provider_id)


def active_provider() -> ModelEvidenceProvider | None:
    """Return the single production provider (or None if the model is
    unavailable, in which case verification is refused upstream)."""
    if not model_service.is_available():
        return None
    if RandomForestProvider.provider_id not in _registry:
        register(RandomForestProvider())
    return _registry[RandomForestProvider.provider_id]


def list_providers() -> list[str]:
    return sorted(_registry)


# Register the production provider eagerly so introspection works even before
# a verification request (prediction still fails fast via model_service).
if RandomForestProvider.provider_id not in _registry:
    register(RandomForestProvider())