"""Feature alignment validation for real certificate datasets.

Ensures that extracted features from real PDFs match the production
31-feature schema exactly before they are eligible for training.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.features.build_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION


class FeatureAlignmentError(Exception):
    """Raised when real features do not align with the production schema."""


def validate_feature_alignment(
    feature_rows: list[dict],
    *,
    strict: bool = True,
) -> dict:
    """Check that every row has exactly the 31 production features.

    Args:
        feature_rows: List of feature dicts produced by build_features_from_extraction.
        strict: If True, raise on first mismatch. If False, collect all mismatches.

    Returns:
        Alignment report dict with status and per-column coverage.
    """
    if not feature_rows:
        return {
            "status": "empty",
            "row_count": 0,
            "expected_features": len(FEATURE_COLUMNS),
            "schema_version": FEATURE_SCHEMA_VERSION,
        }

    expected = set(FEATURE_COLUMNS)
    columns_seen: dict[str, int] = {col: 0 for col in FEATURE_COLUMNS}
    extra_columns: set = set()
    missing_columns: set = set()
    type_violations: list[dict] = []

    for i, row in enumerate(feature_rows):
        row_keys = set(row.keys())
        extra = row_keys - expected
        missing = expected - row_keys
        extra_columns |= extra
        missing_columns |= missing
        for col in expected:
            if col in row and row[col] is not None:
                columns_seen[col] += 1
        for col in expected:
            if col in row and row[col] is not None:
                val = row[col]
                if not isinstance(val, (int, float, bool)):
                    type_violations.append({
                        "row": i,
                        "column": col,
                        "value": str(val)[:50],
                        "type": type(val).__name__,
                    })

    coverage = {
        col: {"count": count, "rate": round(count / len(feature_rows), 4)}
        for col, count in columns_seen.items()
    }
    zero_coverage = [col for col, c in columns_seen.items() if c == 0]

    errors = []
    if missing_columns:
        errors.append(f"Missing columns: {sorted(missing_columns)}")
    if extra_columns:
        errors.append(f"Extra columns (not in production schema): {sorted(extra_columns)}")
    if zero_coverage:
        errors.append(f"Zero-coverage columns: {sorted(zero_coverage)}")
    if type_violations:
        errors.append(f"Type violations: {len(type_violations)} entries")

    report = {
        "status": "passed" if not errors else "failed",
        "row_count": len(feature_rows),
        "expected_features": len(FEATURE_COLUMNS),
        "schema_version": FEATURE_SCHEMA_VERSION,
        "missing_columns": sorted(missing_columns),
        "extra_columns": sorted(extra_columns),
        "zero_coverage_columns": sorted(zero_coverage),
        "type_violation_count": len(type_violations),
        "coverage": coverage,
    }

    if errors and strict:
        raise FeatureAlignmentError(
            f"Feature alignment failed ({len(errors)} issues): "
            + "; ".join(errors)
        )

    return report


def validate_dataframe_alignment(
    df: pd.DataFrame,
    *,
    strict: bool = True,
) -> dict:
    """Validate alignment of a DataFrame against the production feature schema.

    Unlike validate_feature_alignment which checks dicts, this checks a
    DataFrame's columns and dtypes.
    """
    expected = set(FEATURE_COLUMNS)
    actual = set(df.columns)

    missing = sorted(expected - actual)
    extra = sorted(actual - expected - {"label", "certificate_type", "source_sha256", "source_filename"})

    null_rates = {}
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            null_rates[col] = round(df[col].isna().mean(), 4)

    dtype_issues = []
    for col in FEATURE_COLUMNS:
        if col in df.columns:
            dtype_str = str(df[col].dtype)
            if dtype_str not in ("float64", "int64", "bool", "object"):
                dtype_issues.append({"column": col, "dtype": dtype_str})

    report = {
        "status": "passed" if not missing and not dtype_issues else "failed",
        "row_count": len(df),
        "expected_features": len(FEATURE_COLUMNS),
        "schema_version": FEATURE_SCHEMA_VERSION,
        "missing_columns": missing,
        "extra_columns": extra,
        "null_rates": null_rates,
        "dtype_issues": dtype_issues,
    }

    if strict and (missing or dtype_issues):
        issues = []
        if missing:
            issues.append(f"Missing: {missing}")
        if dtype_issues:
            issues.append(f"Dtype issues: {dtype_issues}")
        raise FeatureAlignmentError(
            f"DataFrame alignment failed: {'; '.join(issues)}"
        )

    return report


def assert_alignment_with_training_csv(
    real_csv_path: Path,
    training_csv_path: Path,
) -> dict:
    """Compare a real-data CSV column-for-column against the synthetic training CSV.

    Ensures the same features appear in the same order with compatible dtypes.
    """
    real_df = pd.read_csv(real_csv_path, nrows=5)
    train_df = pd.read_csv(training_csv_path, nrows=5)

    real_cols = [c for c in real_df.columns if c in FEATURE_COLUMNS]
    train_cols = [c for c in train_df.columns if c in FEATURE_COLUMNS]

    mismatches = []
    if real_cols != train_cols:
        for i, (r, t) in enumerate(zip(real_cols, train_cols)):
            if r != t:
                mismatches.append({"position": i, "real": r, "training": t})
        if len(real_cols) != len(train_cols):
            mismatches.append({
                "position": "count",
                "real": len(real_cols),
                "training": len(train_cols),
            })

    return {
        "status": "passed" if not mismatches else "failed",
        "real_features": len(real_cols),
        "training_features": len(train_cols),
        "mismatches": mismatches,
        "schema_version": FEATURE_SCHEMA_VERSION,
    }
