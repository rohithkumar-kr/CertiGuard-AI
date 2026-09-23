"""File storage service: safely persist an uploaded document.

Files are stored under uploads/ with a random name. Original filenames are
kept only as metadata. Sensitive document contents are not indexed here.

Stored files are never served as static content, use random non-guessable
names, and are pruned oldest-first once the retention limit is exceeded so
uploads cannot accumulate without bound.
"""

import os
from pathlib import Path

from app.core.config import settings
from app.utils.file_utils import make_stored_filename, safe_join
from app.core.logging import get_logger

logger = get_logger("file_service")


def save_upload(content: bytes, ext: str) -> Path:
    """Write validated bytes to the upload directory and return the path."""
    settings.ensure_dirs()
    stored_name = make_stored_filename(ext)
    target = safe_join(settings.upload_dir, stored_name)
    target.write_bytes(content)
    _prune_oldest(settings.upload_dir, settings.upload_retention_max)
    logger.info("Stored upload as %s (%d bytes)", stored_name, len(content))
    return target


def delete_upload(path: Path) -> None:
    """Best-effort removal of a stored upload (e.g. after a processing error)."""
    try:
        resolved = (path or Path()).resolve()
        if resolved.is_relative_to(settings.upload_dir.resolve()) and resolved.is_file():
            resolved.unlink(missing_ok=True)
            logger.info("Removed upload %s", resolved.name)
    except OSError as exc:  # noqa: BLE001 - cleanup must never break the response
        logger.warning("Could not remove upload %s: %s", path, exc)


def _prune_oldest(upload_dir: Path, keep: int) -> None:
    """Delete oldest stored uploads so the directory never grows unbounded.

    Keeps only ``keep`` newest files. Non-destructive to any files outside
    the configured upload directory.
    """
    if keep <= 0:
        return
    try:
        files = sorted(
            (p for p in upload_dir.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        )
    except OSError:
        return
    for stale in files[:-keep]:
        try:
            stale.unlink(missing_ok=True)
            logger.info("Pruned old upload %s", stale.name)
        except OSError as exc:  # noqa: BLE001
            logger.warning("Could not prune upload %s: %s", stale, exc)
