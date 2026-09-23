"""Leakage protection for real certificate datasets.

Ensures that real certificate PDFs used for training never appear in the
frozen external validation set, and that no SHA-256 or identity collision
exists across the dataset.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.feedback.leakage import external_validation_hashes, LeakageError
from src.feedback.labels import SPLIT_LABELS


class RealDatasetLeakageError(Exception):
    """Raised when a real certificate dataset violates leakage rules."""


def check_real_dataset_external_overlap(
    manifest_path: Path,
    external_dir: Path,
) -> dict:
    """Verify no SHA-256 in the real dataset manifest matches the external set.

    This is the primary guard: real data must never duplicate frozen evaluation PDFs.

    Raises:
        RealDatasetLeakageError on any match.
    """
    if not manifest_path.exists():
        return {"ok": True, "checked": 0}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    ext_hashes = external_validation_hashes(external_dir)
    ext_sha_set = set(ext_hashes.values())

    real_shas = {
        r.get("sha256")
        for r in manifest.get("records", [])
        if r.get("sha256")
    }

    leaked = sorted(real_shas & ext_sha_set)
    if leaked:
        raise RealDatasetLeakageError(
            f"Leakage: {len(leaked)} real certificate(s) match frozen external "
            f"validation PDFs: {leaked[:5]}"
        )

    return {
        "ok": True,
        "real_count": len(real_shas),
        "external_count": len(ext_sha_set),
        "overlap_count": 0,
    }


def check_real_dataset_duplicates(manifest_path: Path) -> dict:
    """Report duplicate SHA-256 values within the real dataset.

    Informational — does not raise, but warns about intra-dataset duplicates.
    """
    if not manifest_path.exists():
        return {"ok": True, "duplicates": []}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    sha_counts: dict[str, list[dict]] = {}
    for record in manifest.get("records", []):
        sha = record.get("sha256", "")
        sha_counts.setdefault(sha, []).append(record)

    duplicates = []
    for sha, records in sha_counts.items():
        if len(records) > 1:
            duplicates.append({
                "sha256": sha[:16] + "...",
                "count": len(records),
                "labels": [r.get("label") for r in records],
                "filenames": [r.get("original_filename") for r in records],
            })

    return {
        "ok": len(duplicates) == 0,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
    }


def check_real_dataset_split_leakage(
    csv_path: Path,
    external_dir: Path,
) -> dict:
    """Run the existing split leakage checks on a real-data CSV with a split column.

    If the CSV does not have a 'split' column (raw ingestion), this skips
    split checks and only validates external overlap via file fingerprints.
    """
    from src.feedback.leakage import check_split_leakage, check_external_validation_leakage

    if not csv_path.exists():
        return {"ok": True, "skipped": True}

    df = pd.read_csv(csv_path)
    report = {}

    if "split" in df.columns:
        report["split_leakage"] = check_split_leakage(df)
    else:
        report["split_leakage"] = {"ok": True, "skipped": True, "reason": "no split column"}

    if "file_fingerprint" in df.columns:
        report["external_leakage"] = check_external_validation_leakage(df, external_dir)
    else:
        report["external_leakage"] = {
            "ok": True,
            "skipped": True,
            "reason": "no file_fingerprint column",
        }

    return {
        "ok": all(v.get("ok", True) for v in report.values()),
        "checks": report,
    }


def run_real_dataset_leakage_checks(
    base_dir: Path,
    external_dir: Path,
    csv_path: Path | None = None,
) -> dict:
    """Run all leakage protection checks on a real certificate dataset.

    Checks:
        1. SHA-256 overlap with frozen external validation set (FAILS LOUDLY)
        2. Intra-dataset duplicate reporting (informational)
        3. Split leakage if CSV has split column
        4. External validation leakage if CSV has file_fingerprint column

    Returns:
        Aggregated report dict. Raises RealDatasetLeakageError on any hard failure.
    """
    manifest_path = base_dir / "manifest.json"
    results = {}

    # 1. External validation overlap
    results["external_overlap"] = check_real_dataset_external_overlap(
        manifest_path, external_dir
    )

    # 2. Intra-dataset duplicates
    results["duplicates"] = check_real_dataset_duplicates(manifest_path)

    # 3 & 4. Split and external leakage on CSV
    if csv_path and csv_path.exists():
        results["split_and_external"] = check_real_dataset_split_leakage(
            csv_path, external_dir
        )

    all_ok = all(
        v.get("ok", True) if isinstance(v, dict) else True
        for v in results.values()
    )

    return {"ok": all_ok, "checks": results}
