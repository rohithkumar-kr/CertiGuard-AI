"""Lightweight experiment tracking.

Records one JSON line per training run under monitoring/mlruns/runs.jsonl and
maintains a model registry (monitoring/mlruns/model_registry.json) mapping
model versions to their run metadata.

This is intentionally dependency-free (no MLflow server required). The format
is plain JSONL so it can be exported to any tracking system later.
"""

import json
import os
import uuid
from datetime import datetime, timezone

RUNS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "monitoring", "mlruns", "runs.jsonl")
REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "monitoring", "mlruns", "model_registry.json")

DEFAULT_EXPERIMENT = "certificate_fraud_detection"


def _ensure_dir(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def new_run_id():
    return uuid.uuid4().hex[:12]


def log_run(*, model_name, params, metrics, artifacts_dir, model_version=None,
            experiment=DEFAULT_EXPERIMENT, extra=None):
    """Append a run record and update the model registry."""
    _ensure_dir(RUNS_FILE)
    run_id = new_run_id()
    version = model_version or f"{model_name}_{run_id}"
    record = {
        "run_id": run_id,
        "experiment": experiment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "model_version": version,
        "params": params,
        "metrics": metrics,
        "artifacts_dir": artifacts_dir,
        "status": "completed",
    }
    if extra:
        record["extra"] = extra

    with open(RUNS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    _register_model(version, record)
    return record


def _register_model(version, record):
    _ensure_dir(REGISTRY_FILE)
    registry = {}
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (json.JSONDecodeError, OSError):
            registry = {}

    registry[version] = {
        "run_id": record["run_id"],
        "model_name": record["model_name"],
        "timestamp": record["timestamp"],
        "metrics": record["metrics"],
        "artifacts_dir": record["artifacts_dir"],
    }
    with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def load_runs(experiment=DEFAULT_EXPERIMENT):
    if not os.path.exists(RUNS_FILE):
        return []
    runs = []
    with open(RUNS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("experiment") == experiment:
                runs.append(rec)
    return runs


def load_registry():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
