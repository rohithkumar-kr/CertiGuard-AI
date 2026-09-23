"""Tests for real certificate dataset ingestion pipeline.

Covers: PDF discovery, SHA-256 dedup, external validation overlap rejection,
extraction + feature generation, manifest provenance, training CSV schema,
feature alignment, leakage protection, and dry-run validation.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import _make_pdf, GENUINE_PDF_TEXT, SUSPICIOUS_PDF_TEXT

from src.features.build_features import FEATURE_COLUMNS
from src.real_data.ingest import (
    discover_pdfs,
    detect_duplicates,
    _sha256_file,
    _safe_stem,
    check_external_validation_overlap,
    extract_and_build_features,
    build_feature_rows,
    write_training_csv,
    run_ingestion,
)
from src.real_data.feature_alignment import (
    validate_feature_alignment,
    validate_dataframe_alignment,
    FeatureAlignmentError,
)
from src.real_data.schema_validation import (
    validate_training_csv_schema,
    SchemaValidationError,
    dry_run_training_csv,
)
from src.real_data.leakage import (
    check_real_dataset_duplicates,
    check_real_dataset_external_overlap,
    run_real_dataset_leakage_checks,
    RealDatasetLeakageError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def real_dataset_dir(tmp_path: Path) -> Path:
    """Create a temporary real_dataset directory with genuine and suspicious subdirs."""
    base = tmp_path / "real_dataset"
    (base / "genuine").mkdir(parents=True)
    (base / "suspicious").mkdir(parents=True)
    (base / "uncertain").mkdir(parents=True)
    return base


@pytest.fixture()
def ext_validation_dir(tmp_path: Path) -> Path:
    """Create a temporary external validation directory with one PDF."""
    ext_dir = tmp_path / "external_validation"
    ext_dir.mkdir(parents=True)
    (ext_dir / "ext_001.pdf").write_bytes(_make_pdf("EXT-VALIDATION-DOC-001"))
    return ext_dir


@pytest.fixture()
def empty_manifest(real_dataset_dir: Path) -> Path:
    """Write an empty manifest.json."""
    manifest = {
        "version": 1,
        "dataset_type": "real",
        "created_at": None,
        "updated_at": None,
        "records": [],
    }
    path = real_dataset_dir / "manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f)
    return path


# ---------------------------------------------------------------------------
# PDF discovery
# ---------------------------------------------------------------------------

class TestDiscoverPDFs:
    def test_finds_genuine_pdfs(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "cert_001.pdf").write_bytes(_make_pdf("GENUINE-001"))
        entries = discover_pdfs(real_dataset_dir)
        assert len(entries) == 1
        assert entries[0]["label"] == "genuine"
        assert entries[0]["original_filename"] == "cert_001.pdf"

    def test_finds_suspicious_pdfs(self, real_dataset_dir: Path):
        (real_dataset_dir / "suspicious" / "fraud_001.pdf").write_bytes(_make_pdf("FRAUD-001"))
        entries = discover_pdfs(real_dataset_dir)
        assert len(entries) == 1
        assert entries[0]["label"] == "suspicious"

    def test_finds_multiple_directories(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "a.pdf").write_bytes(_make_pdf("A"))
        (real_dataset_dir / "suspicious" / "b.pdf").write_bytes(_make_pdf("B"))
        (real_dataset_dir / "uncertain" / "c.pdf").write_bytes(_make_pdf("C"))
        entries = discover_pdfs(real_dataset_dir)
        assert len(entries) == 3
        labels = {e["label"] for e in entries}
        assert labels == {"genuine", "suspicious", "uncertain"}

    def test_ignores_non_pdf_files(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "readme.txt").write_text("not a pdf")
        (real_dataset_dir / "genuine" / "cert.pdf").write_bytes(_make_pdf("OK"))
        entries = discover_pdfs(real_dataset_dir)
        assert len(entries) == 1

    def test_handles_missing_dirs(self, tmp_path: Path):
        base = tmp_path / "empty"
        base.mkdir()
        entries = discover_pdfs(base)
        assert entries == []


# ---------------------------------------------------------------------------
# SHA-256 + dedup
# ---------------------------------------------------------------------------

class TestDuplicates:
    def test_unique_files(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "a.pdf").write_bytes(_make_pdf("AAA"))
        (real_dataset_dir / "genuine" / "b.pdf").write_bytes(_make_pdf("BBB"))
        entries = discover_pdfs(real_dataset_dir)
        detect_duplicates(entries)
        assert all(e["duplicate_status"] == "unique" for e in entries)

    def test_exact_duplicates(self, real_dataset_dir: Path):
        content = _make_pdf("DUPE")
        (real_dataset_dir / "genuine" / "a.pdf").write_bytes(content)
        (real_dataset_dir / "genuine" / "b.pdf").write_bytes(content)
        entries = discover_pdfs(real_dataset_dir)
        detect_duplicates(entries)
        statuses = [e["duplicate_status"] for e in entries]
        assert all(s == "duplicate" for s in statuses)
        assert entries[0]["duplicate_of"] is not None
        assert entries[1]["duplicate_of"] is not None

    def test_sha256_consistency(self, real_dataset_dir: Path):
        path = real_dataset_dir / "genuine" / "c.pdf"
        path.write_bytes(_make_pdf("HASH"))
        sha1 = _sha256_file(path)
        sha2 = _sha256_file(path)
        assert sha1 == sha2
        assert len(sha1) == 64


# ---------------------------------------------------------------------------
# Safe stem
# ---------------------------------------------------------------------------

class TestSafeStem:
    def test_normal_filename(self):
        assert _safe_stem("my_cert.pdf") == "my_cert"

    def test_special_chars(self):
        result = _safe_stem("cert (1) [copy].pdf")
        assert result == "cert__1___copy_"

    def test_empty(self):
        assert _safe_stem("") == "unnamed"


# ---------------------------------------------------------------------------
# External validation overlap
# ---------------------------------------------------------------------------

class TestExternalOverlap:
    def test_no_overlap(self, real_dataset_dir: Path, ext_validation_dir: Path):
        (real_dataset_dir / "genuine" / "novel.pdf").write_bytes(_make_pdf("NOVEL"))
        entries = discover_pdfs(real_dataset_dir)
        entries = detect_duplicates(entries)
        entries = check_external_validation_overlap(entries, ext_validation_dir)
        assert all(e["duplicate_status"] == "unique" for e in entries)

    def test_overlap_rejected(self, real_dataset_dir: Path, ext_validation_dir: Path):
        ext_content = (ext_validation_dir / "ext_001.pdf").read_bytes()
        (real_dataset_dir / "genuine" / "leak.pdf").write_bytes(ext_content)
        entries = discover_pdfs(real_dataset_dir)
        entries = detect_duplicates(entries)
        entries = check_external_validation_overlap(entries, ext_validation_dir)
        assert entries[0]["duplicate_status"] == "external_validation"
        assert entries[0]["extraction_status"] == "skipped"

    def test_missing_ext_dir(self, real_dataset_dir: Path, tmp_path: Path):
        (real_dataset_dir / "genuine" / "ok.pdf").write_bytes(_make_pdf("OK"))
        entries = discover_pdfs(real_dataset_dir)
        entries = detect_duplicates(entries)
        entries = check_external_validation_overlap(entries, tmp_path / "nonexistent")
        assert all(e["duplicate_status"] == "unique" for e in entries)


# ---------------------------------------------------------------------------
# Feature alignment
# ---------------------------------------------------------------------------

class TestFeatureAlignment:
    def test_perfect_alignment(self):
        row = {col: 0.5 for col in FEATURE_COLUMNS}
        report = validate_feature_alignment([row], strict=True)
        assert report["status"] == "passed"

    def test_missing_column_raises(self):
        row = {col: 0.5 for col in FEATURE_COLUMNS if col != "certificate_type_academic"}
        with pytest.raises(FeatureAlignmentError, match="Missing columns"):
            validate_feature_alignment([row], strict=True)

    def test_extra_column_non_strict(self):
        row = {col: 0.5 for col in FEATURE_COLUMNS}
        row["extra_feature"] = 999
        report = validate_feature_alignment([row], strict=False)
        assert report["status"] == "failed"
        assert "extra_feature" in report["extra_columns"]

    def test_empty_rows(self):
        report = validate_feature_alignment([], strict=True)
        assert report["status"] == "empty"

    def test_dataframe_alignment(self):
        df = pd.DataFrame([{col: 0.5 for col in FEATURE_COLUMNS}])
        report = validate_dataframe_alignment(df, strict=True)
        assert report["status"] == "passed"

    def test_dataframe_missing_column(self):
        cols = [c for c in FEATURE_COLUMNS if c != "certificate_type_academic"]
        df = pd.DataFrame([{col: 0.5 for col in cols}])
        with pytest.raises(FeatureAlignmentError, match="Missing"):
            validate_dataframe_alignment(df, strict=True)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_valid_csv(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS} for _ in range(5)]
        for r in rows:
            r["label"] = 0
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "valid.csv"
        df.to_csv(csv_path, index=False)
        report = validate_training_csv_schema(csv_path, strict=True)
        assert report["status"] == "passed"
        assert report["row_count"] == 5

    def test_missing_label_column(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS} for _ in range(3)]
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "nolabel.csv"
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="Missing required 'label'"):
            validate_training_csv_schema(csv_path, strict=True)

    def test_invalid_label_values(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS} for _ in range(3)]
        for i, r in enumerate(rows):
            r["label"] = i
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "badlabel.csv"
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="invalid values"):
            validate_training_csv_schema(csv_path, strict=True)

    def test_missing_features(self, tmp_path: Path):
        cols = [c for c in FEATURE_COLUMNS if c != "certificate_type_academic"]
        rows = [{col: 0.5 for col in cols} for _ in range(3)]
        for r in rows:
            r["label"] = 0
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "incomplete.csv"
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="Missing"):
            validate_training_csv_schema(csv_path, strict=True)

    def test_null_features(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS} for _ in range(3)]
        rows[0]["certificate_type_academic"] = None
        for r in rows:
            r["label"] = 0
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "nulls.csv"
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="null"):
            validate_training_csv_schema(csv_path, strict=True)

    def test_insufficient_rows(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS}]
        rows[0]["label"] = 0
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "one.csv"
        df.to_csv(csv_path, index=False)
        with pytest.raises(SchemaValidationError, match="at least 2"):
            validate_training_csv_schema(csv_path, strict=True)

    def test_missing_csv(self, tmp_path: Path):
        with pytest.raises(SchemaValidationError, match="CSV not found"):
            validate_training_csv_schema(tmp_path / "nonexistent.csv", strict=True)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_report(self, tmp_path: Path):
        rows = [{col: 0.5 for col in FEATURE_COLUMNS} for _ in range(10)]
        for i, r in enumerate(rows):
            r["label"] = i % 2
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "dry.csv"
        df.to_csv(csv_path, index=False)
        report = dry_run_training_csv(csv_path)
        assert report["dry_run"] is True
        assert report["summary"]["would_pass_training"] is True

    def test_dry_run_fails_on_bad_schema(self, tmp_path: Path):
        df = pd.DataFrame([{"col1": 1, "label": 0}])
        csv_path = tmp_path / "bad.csv"
        df.to_csv(csv_path, index=False)
        report = dry_run_training_csv(csv_path)
        assert report["summary"]["would_pass_training"] is False


# ---------------------------------------------------------------------------
# Leakage protection
# ---------------------------------------------------------------------------

class TestLeakageProtection:
    def test_no_overlap(self, real_dataset_dir: Path, ext_validation_dir: Path):
        manifest = {
            "version": 1,
            "records": [{"sha256": "abc123", "label": "genuine"}],
        }
        (real_dataset_dir / "manifest.json").write_text(json.dumps(manifest))
        report = check_real_dataset_external_overlap(
            real_dataset_dir / "manifest.json", ext_validation_dir
        )
        assert report["ok"] is True

    def test_overlap_raises(self, real_dataset_dir: Path, ext_validation_dir: Path):
        ext_sha = _sha256_file(ext_validation_dir / "ext_001.pdf")
        manifest = {
            "version": 1,
            "records": [{"sha256": ext_sha, "label": "genuine"}],
        }
        (real_dataset_dir / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(RealDatasetLeakageError, match="Leakage"):
            check_real_dataset_external_overlap(
                real_dataset_dir / "manifest.json", ext_validation_dir
            )

    def test_duplicate_detection(self, real_dataset_dir: Path):
        manifest = {
            "version": 1,
            "records": [
                {"sha256": "aaa", "label": "genuine", "original_filename": "a.pdf"},
                {"sha256": "aaa", "label": "genuine", "original_filename": "b.pdf"},
                {"sha256": "bbb", "label": "suspicious", "original_filename": "c.pdf"},
            ],
        }
        (real_dataset_dir / "manifest.json").write_text(json.dumps(manifest))
        report = check_real_dataset_duplicates(real_dataset_dir / "manifest.json")
        assert report["ok"] is False
        assert report["duplicate_count"] == 1

    def test_empty_manifest(self, real_dataset_dir: Path):
        report = check_real_dataset_duplicates(real_dataset_dir / "manifest.json")
        assert report["ok"] is True


# ---------------------------------------------------------------------------
# Write training CSV
# ---------------------------------------------------------------------------

class TestWriteTrainingCSV:
    def test_writes_csv_and_metadata(self, tmp_path: Path):
        rows = [{col: 1.0 for col in FEATURE_COLUMNS} for _ in range(5)]
        for r in rows:
            r["label"] = 0
            r["certificate_type"] = "academic"
        csv_path = tmp_path / "out.csv"
        meta = write_training_csv(rows, csv_path)
        assert csv_path.exists()
        assert meta["row_count"] == 5
        assert meta["genuine_count"] == 5
        assert len(meta["csv_sha256"]) == 64
        meta_path = tmp_path / "out.meta.json"
        assert meta_path.exists()

    def test_empty_rows(self, tmp_path: Path):
        csv_path = tmp_path / "empty.csv"
        meta = write_training_csv([], csv_path)
        assert meta["row_count"] == 0
        assert meta["genuine_count"] == 0
        assert meta["suspicious_count"] == 0


# ---------------------------------------------------------------------------
# Safe stem
# ---------------------------------------------------------------------------

class TestSafeStemExtended:
    def test_long_filename(self):
        result = _safe_stem("a" * 200 + ".pdf")
        assert len(result) == 80


# ---------------------------------------------------------------------------
# Feature rows builder
# ---------------------------------------------------------------------------

class TestBuildFeatureRows:
    def test_builds_rows(self):
        entries = [
            {
                "label": "genuine",
                "feature_extraction_status": "success",
                "features": {col: 0.5 for col in FEATURE_COLUMNS},
                "sha256": "aaa",
                "original_filename": "g.pdf",
            },
            {
                "label": "suspicious",
                "feature_extraction_status": "success",
                "features": {col: 1.0 for col in FEATURE_COLUMNS},
                "sha256": "bbb",
                "original_filename": "s.pdf",
            },
        ]
        rows = build_feature_rows(entries)
        assert len(rows) == 2
        assert rows[0]["label"] == 0
        assert rows[1]["label"] == 1

    def test_skips_uncertain(self):
        entries = [
            {
                "label": "uncertain",
                "feature_extraction_status": "success",
                "features": {col: 0.5 for col in FEATURE_COLUMNS},
                "sha256": "aaa",
                "original_filename": "u.pdf",
            },
        ]
        rows = build_feature_rows(entries)
        assert len(rows) == 0

    def test_skips_failed_features(self):
        entries = [
            {
                "label": "genuine",
                "feature_extraction_status": "failed",
                "features": None,
                "sha256": "aaa",
                "original_filename": "g.pdf",
            },
        ]
        rows = build_feature_rows(entries)
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Full ingestion (end-to-end)
# ---------------------------------------------------------------------------

class TestRunIngestion:
    def test_empty_directory(self, real_dataset_dir: Path):
        report = run_ingestion(real_dataset_dir)
        assert report["status"] == "empty"
        assert report["total_discovered"] == 0

    def test_single_genuine_pdf(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "cert.pdf").write_bytes(
            _make_pdf(GENUINE_PDF_TEXT)
        )
        report = run_ingestion(real_dataset_dir)
        assert report["status"] == "completed"
        assert report["total_discovered"] == 1
        assert report["genuine"] == 1
        assert report["extraction_succeeded"] + report["extraction_failed"] == 1
        assert report["manifest_path"] is not None

    def test_duplicate_detection_in_pipeline(self, real_dataset_dir: Path):
        content = _make_pdf("DUP")
        (real_dataset_dir / "genuine" / "a.pdf").write_bytes(content)
        (real_dataset_dir / "genuine" / "b.pdf").write_bytes(content)
        report = run_ingestion(real_dataset_dir)
        assert report["duplicates"] >= 1
        assert report["total_discovered"] == 2

    def test_external_rejection_in_pipeline(
        self, real_dataset_dir: Path, ext_validation_dir: Path
    ):
        ext_content = (ext_validation_dir / "ext_001.pdf").read_bytes()
        (real_dataset_dir / "genuine" / "leak.pdf").write_bytes(ext_content)
        report = run_ingestion(real_dataset_dir, external_validation_dir=ext_validation_dir)
        assert report["ext_val_rejected"] == 1

    def test_mixed_genuine_suspicious(self, real_dataset_dir: Path):
        (real_dataset_dir / "genuine" / "g.pdf").write_bytes(_make_pdf("GENUINE"))
        (real_dataset_dir / "suspicious" / "s.pdf").write_bytes(_make_pdf("SUSPICIOUS"))
        report = run_ingestion(real_dataset_dir)
        assert report["genuine"] == 1
        assert report["suspicious"] == 1
        assert report["status"] == "completed"
