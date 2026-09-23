"""Training CSV schema compatibility validation.

Provides a dry-run mode that validates a real-data CSV can be safely loaded
by the existing training pipeline (train_model.py) without actually training.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.features.build_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION
from src.data.make_dataset import DATASET_VERSION


class SchemaValidationError(Exception):
    """Raised when the CSV schema is incompatible with the training pipeline."""


def validate_training_csv_schema(
    csv_path: Path,
    *,
    strict: bool = True,
) -> dict:
    """Validate that a CSV matches the schema expected by train_model.py.

    Checks:
        1. All 31 FEATURE_COLUMNS present
        2. 'label' column present with values in {0, 1}
        3. Optional 'certificate_type' column compatible
        4. No null values in FEATURE_COLUMNS
        5. All feature values are numeric (int or float)
        6. Row count >= 2 (minimum for train/test split)
    """
    if not csv_path.exists():
        raise SchemaValidationError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    errors = []
    warnings = []

    # Check required columns
    missing_features = [f for f in FEATURE_COLUMNS if f not in df.columns]
    if missing_features:
        errors.append({
            "check": "missing_features",
            "columns": missing_features,
            "message": f"Missing {len(missing_features)} required feature columns",
        })

    if "label" not in df.columns:
        errors.append({
            "check": "missing_label",
            "message": "Missing required 'label' column",
        })

    # Check label values
    if "label" in df.columns:
        invalid_labels = set(df["label"].dropna().unique()) - {0, 1}
        if invalid_labels:
            errors.append({
                "check": "invalid_labels",
                "values": sorted(str(v) for v in invalid_labels),
                "message": f"Label column contains invalid values: {sorted(invalid_labels)}",
            })

    # Check label balance
    if "label" in df.columns:
        label_counts = df["label"].value_counts()
        min_count = label_counts.min()
        if min_count < 1:
            errors.append({
                "check": "empty_class",
                "message": "One or more label classes has zero rows",
            })
        elif min_count < 2:
            warnings.append({
                "check": "small_class",
                "message": f"One label class has only {min_count} row(s) — train/test split may fail",
            })

    # Check feature nulls
    present_features = [f for f in FEATURE_COLUMNS if f in df.columns]
    null_counts = {}
    for col in present_features:
        nc = int(df[col].isna().sum())
        if nc > 0:
            null_counts[col] = nc
    if null_counts:
        errors.append({
            "check": "null_features",
            "columns": null_counts,
            "message": f"Feature columns contain null values: {null_counts}",
        })

    # Check feature dtypes
    dtype_issues = []
    for col in present_features:
        dtype_str = str(df[col].dtype)
        if dtype_str not in ("float64", "int64", "bool"):
            dtype_issues.append({"column": col, "dtype": dtype_str})
    if dtype_issues:
        errors.append({
            "check": "dtype_mismatch",
            "issues": dtype_issues,
            "message": f"Feature columns have non-numeric dtypes: {dtype_issues}",
        })

    # Check minimum rows
    if len(df) < 2:
        errors.append({
            "check": "insufficient_rows",
            "row_count": len(df),
            "message": "Need at least 2 rows for train/test split",
        })

    # certificate_type compatibility
    cert_type_warn = None
    if "certificate_type" in df.columns:
        unknown_types = set(df["certificate_type"].dropna().unique()) - {
            "academic", "non_academic", "unknown"
        }
        if unknown_types:
            cert_type_warn = {
                "check": "unknown_certificate_types",
                "types": sorted(str(v) for v in unknown_types),
                "message": f"certificate_type has unknown values: {sorted(unknown_types)}",
            }
            warnings.append(cert_type_warn)

    report = {
        "status": "passed" if not errors else "failed",
        "csv_path": str(csv_path),
        "row_count": len(df),
        "column_count": len(df.columns),
        "feature_count": len(present_features),
        "expected_feature_count": len(FEATURE_COLUMNS),
        "label_distribution": {
            str(k): int(v) for k, v in df.get("label", pd.Series(dtype=int)).value_counts().items()
        },
        "errors": errors,
        "warnings": warnings,
        "schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
    }

    if strict and errors:
        raise SchemaValidationError(
            f"Schema validation failed ({len(errors)} errors): "
            + "; ".join(e["message"] for e in errors)
        )

    return report


def dry_run_training_csv(
    csv_path: Path,
    *,
    output_report: Path | None = None,
) -> dict:
    """Validate a CSV in dry-run mode: produce a full compatibility report
    without running the training pipeline.

    This checks schema, distribution, and alignment against the production
    model's feature expectations.
    """
    from src.real_data.feature_alignment import validate_dataframe_alignment

    df = pd.read_csv(csv_path)
    schema_report = validate_training_csv_schema(csv_path, strict=False)
    alignment_report = validate_dataframe_alignment(df, strict=False)

    dry_report = {
        "dry_run": True,
        "schema": schema_report,
        "alignment": alignment_report,
        "summary": {
            "csv_path": str(csv_path),
            "row_count": len(df),
            "genuine_count": int((df.get("label", pd.Series()) == 0).sum()),
            "suspicious_count": int((df.get("label", pd.Series()) == 1).sum()),
            "feature_count": len([f for f in FEATURE_COLUMNS if f in df.columns]),
            "schema_status": schema_report["status"],
            "alignment_status": alignment_report["status"],
            "would_pass_training": (
                schema_report["status"] == "passed"
                and alignment_report["status"] == "passed"
            ),
        },
    }

    if output_report:
        with open(output_report, "w", encoding="utf-8") as f:
            json.dump(dry_report, f, indent=2, default=str)

    return dry_report
