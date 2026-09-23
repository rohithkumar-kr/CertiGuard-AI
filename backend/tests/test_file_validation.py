"""Tests for file validation and safe storage utilities."""

import pytest

from app.core.config import settings
from app.core.errors import FileTooLargeError, FileValidationError
from app.utils import file_utils

VALID_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
VALID_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 20
VALID_JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20


def test_valid_extension_detected():
    assert file_utils.validate_extension("certificate.pdf") == "pdf"
    assert file_utils.validate_extension("cert.PDF") == "pdf"
    assert file_utils.validate_extension("scan.jpg") == "jpg"
    assert file_utils.validate_extension("scan.jpeg") == "jpeg"
    assert file_utils.validate_extension("scan.png") == "png"


def test_unsupported_extension_rejected():
    with pytest.raises(FileValidationError):
        file_utils.validate_extension("evil.exe")
    with pytest.raises(FileValidationError):
        file_utils.validate_extension("cert.txt")
    with pytest.raises(FileValidationError):
        file_utils.validate_extension("noext")


def test_missing_filename_rejected():
    with pytest.raises(FileValidationError):
        file_utils.validate_extension(None)
    with pytest.raises(FileValidationError):
        file_utils.validate_extension("")


def test_magic_bytes_match():
    file_utils.validate_magic_bytes(VALID_PDF, "pdf")
    file_utils.validate_magic_bytes(VALID_PNG, "png")
    file_utils.validate_magic_bytes(VALID_JPG, "jpg")
    file_utils.validate_magic_bytes(VALID_JPG, "jpeg")


def test_magic_bytes_mismatch_rejected():
    with pytest.raises(FileValidationError):
        file_utils.validate_magic_bytes(b"this is not a pdf", "pdf")
    with pytest.raises(FileValidationError):
        file_utils.validate_magic_bytes(VALID_PDF, "png")


def test_empty_file_rejected():
    with pytest.raises(FileValidationError):
        file_utils.validate_file("empty.pdf", b"")


def test_malformed_file_rejected():
    with pytest.raises(FileValidationError):
        file_utils.validate_file("fake.pdf", b"just some text, not a pdf")


def test_valid_file_accepted():
    assert file_utils.validate_file("cert.pdf", VALID_PDF) == "pdf"
    assert file_utils.validate_file("cert.png", VALID_PNG) == "png"


def test_oversized_file_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    big = VALID_PDF + b"0" * (2 * 1024 * 1024)
    with pytest.raises(FileTooLargeError):
        file_utils.validate_file("big.pdf", big)


def test_stored_filename_is_random():
    a = file_utils.make_stored_filename("pdf")
    b = file_utils.make_stored_filename("pdf")
    assert a != b
    assert a.endswith(".pdf")
    assert len(a.split(".")[0]) == 32  # uuid4 hex


def test_safe_join_blocks_traversal():
    from pathlib import Path

    uploads = Path(settings.upload_dir)
    with pytest.raises(FileValidationError):
        file_utils.safe_join(uploads, "../escape.pdf")
    with pytest.raises(FileValidationError):
        file_utils.safe_join(uploads, "..\\escape.pdf")
    ok = file_utils.safe_join(uploads, "abc123.pdf")
    assert ok == uploads / "abc123.pdf"