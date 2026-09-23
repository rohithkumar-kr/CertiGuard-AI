"""File validation utilities.

Validates file extension, size, and magic bytes so that only allowed,
non-dangerous document types are accepted. Prevents path traversal and
oversized uploads.
"""

import os
import uuid
from pathlib import Path

from app.core.errors import FileTooLargeError, FileValidationError
from app.core.config import settings

ALLOWED_MAGIC: dict[str, bytes] = {
    "pdf": b"%PDF",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "jpeg": b"\xff\xd8\xff",
}


def validate_extension(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise FileValidationError("Filename is required.")
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in settings.allowed_upload_extensions:
        raise FileValidationError(
            f"File type '.{ext}' is not allowed. Allowed: {', '.join(sorted(settings.allowed_upload_extensions))}"
        )
    return ext


def validate_magic_bytes(content: bytes, ext: str) -> None:
    if ext not in ALLOWED_MAGIC:
        return
    signature = ALLOWED_MAGIC[ext]
    if not content.startswith(signature):
        raise FileValidationError(
            "File content does not match its extension."
        )


def validate_file(filename: str | None, content: bytes) -> str:
    ext = validate_extension(filename)
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise FileTooLargeError(
            f"File exceeds the {settings.max_upload_size_mb} MB size limit."
        )
    validate_magic_bytes(content, ext)
    return ext


def make_stored_filename(ext: str) -> str:
    """Generate a random, non-guessable stored filename."""
    return f"{uuid.uuid4().hex}.{ext}"


def safe_join(directory: Path, filename: str) -> Path:
    """Join a directory and generated filename, guarding against traversal."""
    target = (directory / filename).resolve()
    if not target.is_relative_to(directory.resolve()):
        raise FileValidationError("Invalid file path.")
    return target
