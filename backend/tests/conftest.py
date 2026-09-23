"""Pytest fixtures and test configuration.

Before importing the app, this module points DATABASE_URL and UPLOAD_DIR at a
temporary location so tests never touch the development database/uploads.
"""

import os
import pathlib
import sys
import tempfile

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="certverify_test_"))

os.environ.setdefault("APP_ENV", "test")
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test_certificates.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.database.database import SessionLocal, get_db  # noqa: E402
from app.main import app  # noqa: E402


def _make_pdf(text: str) -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return bytes(data)


GENUINE_PDF_TEXT = (
    "University of Cambridge\n"
    "Certificate of Achievement\n"
    "\n"
    "We hereby certify that John Walker has completed the Computer Science program.\n"
    "\n"
    "Program offered by University of Cambridge\n"
    "Candidate ID: CERT-2022-123455\n"
    "Marks: 95 out of 100\n"
    "Grade: A\n"
    "Issue Date: 2022-06-15\n"
    "Signature: ____________________\n"
    "Seal: University Seal\n"
    "QR code available for verification\n"
)

SUSPICIOUS_PDF_TEXT = (
    "Online Degree Emporium\n"
    "Instant Certificate\n"
    "\n"
    "Buy verified certificates online. No exam needed, instant delivery.\n"
    "Get your Computer Science certificate free, contact us on whatsapp @certseller.\n"
    "\n"
    "Candidate ID: FREECERT-2022-999999\n"
    "Marks: 150 out of 100\n"
    "Grade: A\n"
    "Issue Date: 2026-12-01\n"
)

# A legitimate corporate course-completion certificate mirroring the real
# uploaded AWS training certificate structure (generic phrasing, no
# university/academic markers, human-readable date, "Awarded to" recipient).
COMPLETION_PDF_TEXT = (
    "AWS Training & Certification\n"
    "Director, AWS Training & Certification\n"
    "\n"
    "Securely Connecting AWS IoT Devices to the Cloud\n"
    "Completed: September 14, 2025\n"
    "Completion Certificate\n"
    "Awarded to\n"
    "Rohith Kumar K R\n"
)

# A technical certificate: certification context + a technical domain.
TECHNICAL_PDF_TEXT = (
    "CloudForge Academy\n"
    "Technical Certification\n"
    "\n"
    "This certifies that Meera Patel has demonstrated proficiency in Cloud Computing.\n"
    "Certification Code: CERT-2023-654321\n"
    "Issued by CloudForge Academy\n"
    "Issue Date: 2023-03-10\n"
    "Signature: ____________\n"
)

# A workshop / attendance certificate (low-stakes).
WORKSHOP_PDF_TEXT = (
    "Innovate Academy\n"
    "Seminar Participation Certificate\n"
    "\n"
    "This certifies that Arjun Mehta attended the Data Science Workshop.\n"
    "Issued by Innovate Academy\n"
    "Issue Date: 2024-02-20\n"
    "Signature: ____________\n"
)

# Unknown issuer, no academic markers.
UNKNOWN_ISSUER_PDF_TEXT = (
    "Mystery Certifications Ltd\n"
    "Certificate of Completion\n"
    "\n"
    "We hereby certify that Priya Sharma has completed the Leadership program.\n"
    "Offered by Mystery Certifications Ltd\n"
    "Issue Date: 2023-05-05\n"
)

# Missing recipient (no recipient name extracted).
MISSING_RECIPIENT_PDF_TEXT = (
    "University of Oxford\n"
    "Certificate of Achievement\n"
    "\n"
    "This certificate acknowledges completion of the Physics program.\n"
    "Offered by University of Oxford\n"
    "Candidate ID: CERT-2021-111222\n"
    "Marks: 88 out of 100\n"
    "Grade: B\n"
    "Issue Date: 2021-08-10\n"
    "Signature: ____________\n"
)

# Inconsistent grade/marks (grade B but 91/100) and future date.
INCONSISTENT_PDF_TEXT = (
    "University of Cambridge\n"
    "Certificate of Achievement\n"
    "\n"
    "We hereby certify that Nina Gupta has completed the Data Science program.\n"
    "Offered by University of Cambridge\n"
    "Candidate ID: CERT-2024-987654\n"
    "Marks: 91 out of 100\n"
    "Grade: B\n"
    "Issue Date: 2027-06-15\n"
    "Signature: ____________\n"
)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def genuine_pdf() -> bytes:
    return _make_pdf(GENUINE_PDF_TEXT)


@pytest.fixture(scope="session")
def suspicious_pdf() -> bytes:
    return _make_pdf(SUSPICIOUS_PDF_TEXT)


@pytest.fixture(scope="session")
def completion_pdf() -> bytes:
    return _make_pdf(COMPLETION_PDF_TEXT)


@pytest.fixture(scope="session")
def technical_pdf() -> bytes:
    return _make_pdf(TECHNICAL_PDF_TEXT)


@pytest.fixture(scope="session")
def workshop_pdf() -> bytes:
    return _make_pdf(WORKSHOP_PDF_TEXT)


@pytest.fixture(scope="session")
def unknown_issuer_pdf() -> bytes:
    return _make_pdf(UNKNOWN_ISSUER_PDF_TEXT)


@pytest.fixture(scope="session")
def missing_recipient_pdf() -> bytes:
    return _make_pdf(MISSING_RECIPIENT_PDF_TEXT)


@pytest.fixture(scope="session")
def inconsistent_pdf() -> bytes:
    return _make_pdf(INCONSISTENT_PDF_TEXT)