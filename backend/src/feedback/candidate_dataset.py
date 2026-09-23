"""Candidate training dataset builder (Phase 9D).

Converts reviewed examples (human feedback) into a candidate training dataset.

Rules enforced:
  - only ``confirmed_genuine`` and ``confirmed_suspicious`` qualify
  - ``uncertain`` and ``not_reviewed`` examples are excluded
  - original metadata is preserved (verification id, prediction snapshot,
    reviewer label, certificate type, issuer, fingerprints, ...)
  - duplicate samples are prevented
  - train/test split metadata is preserved and assigned leakage-safely
  - leakage is checked and FAILS LOUDLY (LeakageError)

The output is a candidate dataset CSV + a report. It is NOT a production model
and it never promotes anything.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.feedback import QUALIFYING_LABELS, VerificationFeedback
from app.models.verification import Verification
from src.features.build_features import FEATURE_COLUMNS
from src.feedback.labels import CANDIDATE_DATA_DIR, DEFAULT_TEST_FRACTION
from src.feedback.leakage import check_all, report_duplicates
from src.feedback.splitter import assign_splits

logger = get_logger("candidate_dataset")

REVIEWED_LABEL_TO_TARGET = {"confirmed_genuine": 0, "confirmed_suspicious": 1}


def _snapshot_features(verification: Verification) -> dict | None:
    """Return the stored 31-feature vector from the intelligence snapshot."""
    raw = verification.intelligence_json
    if not raw:
        return None
    try:
        snapshot = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(snapshot, dict):
        return None
    features = snapshot.get("features")
    return features if isinstance(features, dict) else None


def _recompute_features(verification: Verification) -> dict | None:
    """Recompute features from the stored file when no snapshot exists."""
    certificate = verification.certificate
    if certificate is None or not certificate.file_path:
        return None
    path = Path(certificate.file_path)
    if not path.exists():
        return None
    try:
        from app.services.extraction_service import extract_document
        from app.services.feature_service import build_features_from_extraction
        from app.utils.file_utils import validate_file

        content = path.read_bytes()
        ext = validate_file(path.name, content)
        extraction = extract_document(str(path), ext)
        return build_features_from_extraction(extraction)
    except Exception:  # noqa: BLE001 - best effort for legacy rows
        logger.warning("Could not recompute features for %s", verification.verification_id)
        return None


def collect_reviewed_rows(db: Session) -> list[dict]:
    """Gather qualifying reviewed rows with metadata + feature vectors."""
    feedback_rows = (
        db.query(VerificationFeedback)
        .filter(VerificationFeedback.reviewer_label.in_(QUALIFYING_LABELS))
        .all()
    )
    verifications = {
        v.verification_id: v
        for v in db.query(Verification)
        .filter(Verification.verification_id.in_([f.verification_id for f in feedback_rows]))
        .all()
    }

    records = []
    for fb in feedback_rows:
        verification = verifications.get(fb.verification_id)
        if verification is None:
            logger.warning("Feedback %s has no matching verification; skipping", fb.verification_id)
            continue

        features = _snapshot_features(verification)
        features_available = True
        if features is None:
            features = _recompute_features(verification)
            features_available = features is not None

        row = {
            "verification_id": fb.verification_id,
            "reviewer_label": fb.reviewer_label,
            "reviewer_note": fb.reviewer_note or "",
            "reviewed_at": fb.reviewed_at.isoformat() if fb.reviewed_at else None,
            "original_prediction": fb.original_prediction,
            "original_risk_score": fb.original_risk_score,
            "original_confidence": fb.original_confidence,
            "model_version": fb.model_version,
            "certificate_type": fb.certificate_type or "unknown",
            "extraction_completeness": fb.extraction_completeness,
            "review_status": fb.review_status or "",
            "issuer": fb.issuer or "",
            "ood_status": fb.ood_status or "",
            "review_priority": fb.review_priority or "",
            "is_disagreement": int(bool(fb.is_disagreement)),
            "file_fingerprint": fb.file_fingerprint or "",
            "cert_id_fingerprint": fb.cert_id_fingerprint or "",
            "identity_fingerprint": fb.identity_fingerprint or "",
            "certificate_id": _certificate_id(verification),
            "label": REVIEWED_LABEL_TO_TARGET[fb.reviewer_label],
            "features_available": features_available,
        }
        for col in FEATURE_COLUMNS:
            value = features.get(col) if features else None
            row[col] = value if value is not None else None
        records.append(row)
    return records


def _certificate_id(verification: Verification) -> str:
    try:
        fields = json.loads(verification.extracted_info or "{}")
    except (ValueError, TypeError):
        return ""
    return str(fields.get("cert_id") or "")


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove exact duplicate samples (same verification id or same identity).

    Duplicates are detected on the fingerprint set. The first occurrence of a
    duplicate group is kept. The count is reported.
    """
    before = len(df)
    if df.empty:
        return df, 0
    keys = ["file_fingerprint", "cert_id_fingerprint", "identity_fingerprint"]
    present = [k for k in keys if k in df.columns]
    # Rows that share any fingerprint are considered the same sample family.
    deduped = df.drop_duplicates(subset=["verification_id"])
    deduped = deduped.drop_duplicates(subset=present) if present else deduped
    return deduped, before - len(deduped)


def build_candidate_dataset(
    db: Session,
    output_dir: Path | str,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    seed: int = 42,
    dataset_batch: str | None = None,
    external_dir: Path | str | None = None,
) -> dict:
    """Build and write the candidate dataset + report.

    Returns the report dict. Raises LeakageError if any leakage is detected.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batch = dataset_batch or (
        "reviewed-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    )
    rows = collect_reviewed_rows(db)
    if not rows:
        report = {
            "dataset_batch": batch,
            "qualified_rows": 0,
            "message": "No qualifying reviewed samples (need confirmed_genuine or confirmed_suspicious).",
            "candidate_dataset": None,
        }
        return report

    df = pd.DataFrame(rows)
    df, removed_duplicates = _dedupe(df)
    df = assign_splits(df, test_fraction=test_fraction, seed=seed)
    df["dataset_batch"] = batch

    dataset_path = output_dir / f"{batch}.csv"
    report_path = output_dir / f"{batch}_report.json"
    df.to_csv(dataset_path, index=False)

    leakage = check_all(df, external_dir=external_dir)
    duplicates_report = report_duplicates(df)

    split_counts = df["split"].value_counts().to_dict()
    report = {
        "dataset_batch": batch,
        "qualified_rows": len(rows),
        "rows_written": int(len(df)),
        "duplicate_rows_removed": int(removed_duplicates),
        "class_balance": {
            "confirmed_genuine": int((df["reviewer_label"] == "confirmed_genuine").sum()),
            "confirmed_suspicious": int((df["reviewer_label"] == "confirmed_suspicious").sum()),
        },
        "split_counts": {k: int(v) for k, v in split_counts.items()},
        "features_available": int(df["features_available"].sum()),
        "features_total": int(len(df)),
        "feature_schema": "v3",
        "feature_count": len(FEATURE_COLUMNS),
        "missing_feature_rows": int((~df["features_available"]).sum()),
        "certificate_type_balance": df["certificate_type"].value_counts().to_dict(),
        "issuer_diversity": int(df["issuer"].nunique()),
        "leakage": leakage,
        "duplicates": duplicates_report,
        "candidate_dataset": str(dataset_path),
        "seed": seed,
        "test_fraction": test_fraction,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Persist the split + batch assignment back onto the feedback rows.
    split_by_id = dict(zip(df["verification_id"], df["split"]))
    feedback_rows = (
        db.query(VerificationFeedback)
        .filter(VerificationFeedback.verification_id.in_(split_by_id.keys()))
        .all()
    )
    for fb in feedback_rows:
        fb.split = split_by_id[fb.verification_id]
        fb.dataset_batch = batch
    db.commit()

    logger.info(
        "Candidate dataset written: %s (%d rows, %d removed duplicates)",
        dataset_path, len(df), removed_duplicates,
    )
    return report