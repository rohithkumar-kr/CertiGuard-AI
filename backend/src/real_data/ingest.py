"""Real certificate dataset ingestion pipeline.

Discovers labeled PDFs under the real_dataset directory structure, runs the
production extraction and feature-generation paths, detects duplicates, and
produces a training-compatible CSV with full provenance tracking.

This module never modifies the production model, feature schema, or
external validation set.

Usage::

    python -m src.real_data.ingest --base-dir ./data/real_dataset

Output:
    data/processed/real_features.csv
    data/real_dataset/manifest.json (updated)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.features.build_features import FEATURE_COLUMNS
from src.feedback.leakage import external_validation_hashes

_EXTRACTABLE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

_LABEL_TO_DIR = {
    "genuine": "genuine",
    "suspicious": "suspicious",
    "uncertain": "uncertain",
}

_LABEL_TO_TARGET = {
    "genuine": 0,
    "suspicious": 1,
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return safe[:80] or "unnamed"


def discover_pdfs(base_dir: Path) -> list[dict]:
    """Find all PDF/image files under genuine/suspicious/uncertain directories.

    Returns list of dicts with: path, label, original_filename.
    """
    entries = []
    for label, subdir in _LABEL_TO_DIR.items():
        label_dir = base_dir / subdir
        if not label_dir.exists():
            continue
        for path in sorted(label_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _EXTRACTABLE_EXTENSIONS:
                continue
            entries.append({
                "path": path,
                "label": label,
                "original_filename": path.name,
            })
    return entries


def detect_duplicates(entries: list[dict]) -> list[dict]:
    """Compute SHA-256 for each entry and mark exact duplicates.

    Modifies entries in place, adding sha256 and duplicate_status fields.
    Returns the entries with duplicate_status set.
    """
    sha_to_ids: dict[str, list[int]] = {}
    for i, entry in enumerate(entries):
        sha = _sha256_file(entry["path"])
        entry["sha256"] = sha
        sha_to_ids.setdefault(sha, []).append(i)

    for i, entry in enumerate(entries):
        siblings = sha_to_ids[entry["sha256"]]
        if len(siblings) > 1:
            entry["duplicate_status"] = "duplicate"
            entry["duplicate_of"] = siblings[0] if siblings[0] != i else siblings[1]
        else:
            entry["duplicate_status"] = "unique"
            entry["duplicate_of"] = None
    return entries


def check_external_validation_overlap(
    entries: list[dict], external_dir: Path
) -> list[dict]:
    """Reject any entry whose SHA-256 matches a frozen external validation PDF.

    Sets duplicate_status="external_validation" for matches.
    """
    if not external_dir.exists():
        return entries
    ext_hashes = set(external_validation_hashes(external_dir).values())
    for entry in entries:
        if entry.get("sha256") in ext_hashes:
            entry["duplicate_status"] = "external_validation"
            entry["extraction_status"] = "skipped"
            entry["feature_extraction_status"] = "skipped"
    return entries


def extract_and_build_features(entry: dict) -> dict:
    """Run the production extraction and feature generation on a single PDF.

    Uses the exact same code paths as the FastAPI runtime:
    - app.services.extraction_service.extract_document()
    - app.services.feature_service.build_features_from_extraction()

    Adds extraction_status, feature_extraction_status, features, and
    extraction metadata to the entry dict.
    """
    if entry.get("duplicate_status") in ("duplicate", "external_validation"):
        entry["extraction_status"] = "skipped"
        entry["feature_extraction_status"] = "skipped"
        entry["features"] = None
        return entry

    path = entry["path"]
    ext = path.suffix.lower().lstrip(".")

    try:
        from app.services.extraction_service import extract_document
        extraction = extract_document(str(path), ext)
        entry["extraction_status"] = "success"
        entry["extraction_method"] = extraction.extraction_method
        entry["extraction_completeness"] = extraction.extraction_completeness
        entry["extracted_text_length"] = extraction.extracted_text_length
        entry["extraction_warnings"] = extraction.warnings
    except Exception as exc:
        entry["extraction_status"] = "failed"
        entry["extraction_error"] = str(exc)[:200]
        entry["features"] = None
        entry["feature_extraction_status"] = "skipped"
        return entry

    try:
        from app.services.feature_service import build_features_from_extraction
        features = build_features_from_extraction(extraction)
        entry["features"] = features
        entry["feature_extraction_status"] = "success"
    except Exception as exc:
        entry["feature_extraction_status"] = "failed"
        entry["feature_error"] = str(exc)[:200]
        entry["features"] = None

    return entry


def build_feature_rows(entries: list[dict]) -> list[dict]:
    """Convert extracted features into flat rows for the training CSV.

    Only includes entries with label in {genuine, suspicious} and
    successfully extracted features.
    """
    rows = []
    for entry in entries:
        if entry.get("feature_extraction_status") != "success":
            continue
        if entry["label"] not in _LABEL_TO_TARGET:
            continue
        features = entry.get("features")
        if features is None:
            continue
        row = {}
        for col in FEATURE_COLUMNS:
            row[col] = features.get(col)
        row["label"] = _LABEL_TO_TARGET[entry["label"]]
        row["certificate_type"] = entry.get("certificate_type", "unknown")
        row["source_sha256"] = entry.get("sha256", "")
        row["source_filename"] = _safe_stem(entry.get("original_filename", ""))
        rows.append(row)
    return rows


def update_manifest(base_dir: Path, entries: list[dict]) -> Path:
    """Write the updated manifest.json with full provenance for every entry."""
    manifest_path = base_dir / "manifest.json"
    now = datetime.now(timezone.utc).isoformat()

    records = []
    for entry in entries:
        record = {
            "file_id": uuid.uuid5(uuid.NAMESPACE_URL, entry.get("sha256", "")).hex[:16],
            "sha256": entry.get("sha256", ""),
            "label": entry["label"],
            "original_filename": entry.get("original_filename", ""),
            "source_dir": str(entry["path"].parent.name),
            "extraction_status": entry.get("extraction_status", "pending"),
            "feature_extraction_status": entry.get("feature_extraction_status", "pending"),
            "duplicate_status": entry.get("duplicate_status", "pending"),
            "ingested_at": now,
        }
        if entry.get("extraction_method"):
            record["extraction_method"] = entry["extraction_method"]
        if entry.get("extraction_completeness") is not None:
            record["extraction_completeness"] = entry["extraction_completeness"]
        if entry.get("extraction_warnings"):
            record["extraction_warnings"] = entry["extraction_warnings"]
        if entry.get("duplicate_of") is not None:
            record["duplicate_of_index"] = entry["duplicate_of"]
        records.append(record)

    manifest = {
        "version": 1,
        "dataset_type": "real",
        "created_at": records[0]["ingested_at"] if records else None,
        "updated_at": now,
        "total_records": len(records),
        "genuine_count": sum(1 for r in records if r["label"] == "genuine"),
        "suspicious_count": sum(1 for r in records if r["label"] == "suspicious"),
        "uncertain_count": sum(1 for r in records if r["label"] == "uncertain"),
        "extraction_success_count": sum(1 for r in records if r["extraction_status"] == "success"),
        "feature_success_count": sum(1 for r in records if r["feature_extraction_status"] == "success"),
        "unique_count": sum(1 for r in records if r["duplicate_status"] == "unique"),
        "duplicate_count": sum(1 for r in records if r["duplicate_status"] == "duplicate"),
        "external_validation_rejected": sum(
            1 for r in records if r["duplicate_status"] == "external_validation"
        ),
        "schema": {
            "required_fields": [
                "file_id", "sha256", "label", "original_filename",
                "source_dir", "extraction_status", "feature_extraction_status",
                "duplicate_status", "ingested_at",
            ],
            "label_values": ["genuine", "suspicious", "uncertain"],
            "extraction_status_values": ["success", "failed", "skipped", "pending"],
            "duplicate_status_values": ["unique", "duplicate", "external_validation", "pending"],
        },
        "records": records,
    }

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    return manifest_path


def write_training_csv(
    rows: list[dict], output_path: Path, metadata: dict | None = None
) -> dict:
    """Write the training-compatible CSV and accompanying metadata.

    Returns a metadata dict with dataset statistics.
    """
    if not rows:
        return {
            "dataset_version": "real_v1",
            "dataset_type": "real",
            "row_count": 0,
            "genuine_count": 0,
            "suspicious_count": 0,
            "feature_version": "v3",
            "feature_count": len(FEATURE_COLUMNS),
            "output_path": str(output_path),
        }

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    genuine_count = int((df["label"] == 0).sum())
    suspicious_count = int((df["label"] == 1).sum())

    csv_bytes = output_path.read_bytes()
    csv_hash = hashlib.sha256(csv_bytes).hexdigest()

    meta = {
        "dataset_version": "real_v1",
        "dataset_type": "real",
        "row_count": len(df),
        "genuine_count": genuine_count,
        "suspicious_count": suspicious_count,
        "uncertain_count": 0,
        "feature_version": "v3",
        "feature_count": len(FEATURE_COLUMNS),
        "feature_names": FEATURE_COLUMNS,
        "csv_sha256": csv_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(output_path),
    }
    if metadata:
        meta.update(metadata)

    meta_path = output_path.with_suffix(".meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    return meta


def run_ingestion(
    base_dir: str | Path,
    external_validation_dir: str | Path | None = None,
    output_csv: str | Path | None = None,
) -> dict:
    """Run the full ingestion pipeline and return a summary report.

    Steps:
        1. Discover PDFs under genuine/suspicious/uncertain
        2. Compute SHA-256 and detect duplicates
        3. Reject frozen external validation overlaps
        4. Run production extraction + feature generation
        5. Build feature rows (genuine/suspicious only)
        6. Write training CSV + metadata
        7. Update manifest.json

    Returns a summary dict with counts and paths.
    """
    base = Path(base_dir)
    if external_validation_dir is None:
        external_validation_dir = base.parent / "external_validation"
    ext_dir = Path(external_validation_dir)

    if output_csv is None:
        output_csv = base.parent / "processed" / "real_features.csv"
    csv_path = Path(output_csv)

    # Step 1: discover
    entries = discover_pdfs(base)
    if not entries:
        report = {
            "status": "empty",
            "message": "No PDFs found under genuine/, suspicious/, or uncertain/ directories.",
            "total_discovered": 0,
        }
        write_training_csv([], csv_path, metadata=report)
        update_manifest(base, [])
        return report

    # Step 2: SHA-256 + duplicates
    entries = detect_duplicates(entries)

    # Step 3: external validation overlap
    entries = check_external_validation_overlap(entries, ext_dir)

    # Step 4: extraction + features
    for entry in entries:
        extract_and_build_features(entry)

    # Step 5: build rows
    rows = build_feature_rows(entries)

    # Step 6: write CSV
    summary = {
        "total_discovered": len(entries),
        "genuine": sum(1 for e in entries if e["label"] == "genuine"),
        "suspicious": sum(1 for e in entries if e["label"] == "suspicious"),
        "uncertain": sum(1 for e in entries if e["label"] == "uncertain"),
        "unique": sum(1 for e in entries if e.get("duplicate_status") == "unique"),
        "duplicates": sum(1 for e in entries if e.get("duplicate_status") == "duplicate"),
        "ext_val_rejected": sum(
            1 for e in entries if e.get("duplicate_status") == "external_validation"
        ),
        "extraction_succeeded": sum(1 for e in entries if e.get("extraction_status") == "success"),
        "extraction_failed": sum(1 for e in entries if e.get("extraction_status") == "failed"),
        "features_succeeded": sum(
            1 for e in entries if e.get("feature_extraction_status") == "success"
        ),
        "features_failed": sum(
            1 for e in entries if e.get("feature_extraction_status") == "failed"
        ),
        "training_rows": len(rows),
    }
    meta = write_training_csv(rows, csv_path, metadata=summary)
    summary["csv_path"] = str(csv_path)
    summary["csv_hash"] = meta.get("csv_sha256")
    summary["meta_path"] = str(csv_path.with_suffix(".meta.json"))

    # Step 7: update manifest
    manifest_path = update_manifest(base, entries)
    summary["manifest_path"] = str(manifest_path)
    summary["status"] = "completed"

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest real certificate PDFs into a training-compatible dataset"
    )
    parser.add_argument(
        "--base-dir",
        default=os.environ.get("REAL_DATASET_DIR", "./data/real_dataset"),
        help="Root of the real_dataset directory (contains genuine/, suspicious/, uncertain/)",
    )
    parser.add_argument(
        "--external-validation-dir",
        default=None,
        help="Path to the frozen 27-PDF external validation set (default: ../external_validation)",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Output path for the training CSV (default: data/processed/real_features.csv)",
    )
    args = parser.parse_args()

    report = run_ingestion(
        base_dir=args.base_dir,
        external_validation_dir=args.external_validation_dir,
        output_csv=args.output_csv,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
