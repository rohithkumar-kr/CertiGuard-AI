"""Leakage protection for reviewed datasets (Phase 9K).

Checks that a candidate dataset built from reviewed feedback does not leak:

  - the same certificate (file fingerprint) across train and test
  - the same certificate ID across splits
  - the same identity (recipient+issuer+course+date) across splits when
    inappropriate
  - any reviewed example that also appears in the frozen external validation
    set (feedback examples must never leak into frozen external validation)

``check_split_leakage`` FAILS LOUDLY: it raises LeakageError (not just logs) so
a dataset with leakage is never silently promoted to training use.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from src.feedback.labels import SPLIT_LABELS

SPLIT_PAIRS = (("train", "test"),)
_FP_COLUMNS = ("file_fingerprint", "cert_id_fingerprint", "identity_fingerprint")


class LeakageError(Exception):
    """Raised when a dataset violates a leakage rule."""


def _shared_values(df: pd.DataFrame, column: str, splits: tuple[str, ...]) -> list[str]:
    """Return values of ``column`` present in more than one split."""
    per_split: dict[str, set] = {}
    for split in splits:
        subset = df[df["split"] == split]
        values = {str(v) for v in subset[column].dropna().tolist() if str(v).strip()}
        per_split[split] = values
    shared: set = set()
    listed = list(splits)
    for i in range(len(listed)):
        for j in range(i + 1, len(listed)):
            shared |= per_split[listed[i]] & per_split[listed[j]]
    return sorted(shared)


def check_split_leakage(df: pd.DataFrame) -> dict:
    """Verify no fingerprint / certificate ID appears in more than one split.

    Raises LeakageError on the first offending rule. Returns a report dict on
    success.
    """
    if df.empty:
        return {"ok": True, "checks": {}}
    if "split" not in df.columns:
        raise LeakageError("Dataset has no 'split' column; refusing to validate.")
    known = set(SPLIT_LABELS)
    present = {s for s in df["split"].dropna().unique()}
    unknown = present - known
    if unknown:
        raise LeakageError(f"Dataset contains unknown split values: {sorted(unknown)}")

    report: dict = {}
    for column in ("certificate_id", *_FP_COLUMNS):
        if column not in df.columns:
            continue
        shared = _shared_values(df, column, ("train", "test"))
        report[column] = {"cross_split_values": len(shared), "ok": not shared}
        if shared:
            raise LeakageError(
                f"Leakage detected: {len(shared)} value(s) of '{column}' appear in "
                f"both train and test, e.g. {shared[:5]}."
            )
    return {"ok": True, "checks": report}


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def external_validation_hashes(external_dir: Path) -> dict[str, str]:
    """Map every file in the external validation directory to its SHA-256."""
    hashes: dict[str, str] = {}
    if not external_dir.exists():
        return hashes
    for path in sorted(external_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"}:
            try:
                hashes[str(path.name)] = _file_hash(path)
            except OSError:
                continue
    return hashes


def check_external_validation_leakage(
    df: pd.DataFrame, external_dir: Path
) -> dict:
    """Ensure reviewed-example file fingerprints do not match frozen external
    validation documents. Raises LeakageError when a match is found."""
    if df.empty or "file_fingerprint" not in df.columns:
        return {"ok": True, "external_hashes": {}}
    hashes = external_validation_hashes(external_dir)
    dataset_fps = {str(v) for v in df["file_fingerprint"].dropna().tolist() if str(v).strip()}
    leaked = sorted(h for h in hashes.values() if h in dataset_fps)
    if leaked:
        raise LeakageError(
            f"Leakage detected: {len(leaked)} reviewed example(s) appear in the "
            "frozen external validation set. Reviewed feedback must never be "
            "trained on frozen external validation documents."
        )
    return {"ok": True, "external_hashes": hashes, "checked": len(dataset_fps)}


def check_all(df: pd.DataFrame, external_dir: Path | None = None) -> dict:
    """Run all leakage checks. Raises LeakageError on any violation."""
    split_report = check_split_leakage(df)
    external_report = {"ok": True}
    if external_dir is not None:
        external_report = check_external_validation_leakage(df, Path(external_dir))
    return {"split": split_report, "external": external_report}


def report_duplicates(df: pd.DataFrame) -> dict:
    """Report intra-dataset duplicate counts (informational, not a failure)."""
    out: dict = {}
    for column in ("certificate_id", *_FP_COLUMNS):
        if column not in df.columns:
            continue
        counts = df[column].dropna().value_counts()
        duplicated = counts[counts > 1]
        out[column] = {
            "duplicate_groups": int(len(duplicated)),
            "affected_rows": int(duplicated.sum() - len(duplicated)),
        }
    return out