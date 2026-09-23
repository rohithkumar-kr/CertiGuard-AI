"""Runtime model loading and prediction wrapper.

Loads the serialized artifacts (model pipeline + feature list + metadata)
once and caches them. If artifacts are missing, calls fail with a
ModelUnavailableError instead of crashing the app.
"""

import json
import os
import threading

from app.core.config import settings
from app.core.errors import ModelUnavailableError
from app.core.logging import get_logger
from src.inference.predict import load_model, predict as infer_predict

logger = get_logger("model")

_lock = threading.Lock()
_cache = {"pipeline": None, "features": None, "metadata": None}


def _metadata_path():
    return settings.model_metadata_dir / "model_metadata.json"


def load() -> tuple:
    """Load and cache (pipeline, features, metadata)."""
    with _lock:
        if _cache["pipeline"] is not None:
            return _cache["pipeline"], _cache["features"], _cache["metadata"]

        if not (settings.model_artifact_dir / "model.joblib").exists():
            raise ModelUnavailableError()

        pipeline, features = load_model(str(settings.model_artifact_dir))
        metadata = None
        if _metadata_path().exists():
            with open(_metadata_path(), "r", encoding="utf-8") as f:
                metadata = json.load(f)

        _cache.update(pipeline=pipeline, features=features, metadata=metadata)
        logger.info(
            "Model loaded: %s (%d features)",
            metadata.get("model_version") if metadata else settings.model_version,
            len(features),
        )
        return pipeline, features, metadata


def model_version() -> str:
    try:
        _, _, metadata = load()
        if metadata and metadata.get("model_version"):
            return metadata["model_version"]
    except ModelUnavailableError:
        pass
    return settings.model_version


def is_available() -> bool:
    return (settings.model_artifact_dir / "model.joblib").exists()


def model_info() -> dict:
    _, features, metadata = load()
    info = {
        "model_version": model_version(),
        "model_name": (metadata or {}).get("model_name", "unknown"),
        "features": features,
        "metrics": ((metadata or {}).get("metrics") or {}).get("test", {}),
        "created_at": (metadata or {}).get("created_at"),
    }
    return info


def predict(features: dict) -> dict:
    _, _, _ = load()  # ensure available
    result = infer_predict(
        features, str(settings.model_artifact_dir), threshold=settings.decision_threshold
    )
    result["model_version"] = model_version()
    return result