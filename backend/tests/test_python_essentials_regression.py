"""Regression tests for the image-heavy Python Essentials false positive.

The certificate `PythonEssentials1Update20250123-28-a15e7b.pdf` embeds only a
44-char text layer ("ROHITH KUMAR K R IT" / "Issued on: Jan 23, 2025") and
relies on OCR. RapidOCR returned the sentence "...provided by Cisco Networking
Academy in collaboration with OpenEDG Python Institute." — the issuer marker
captured 61 characters, exceeding the 60-char issuer cap, so the organization
was rejected as "generic" and `issuer_present=0` pushed risk to ~0.78.

Fix: `ISSUER_CLAUSE_SPLIT_RE` now also truncates issuer captures at
collaboration/partnership/association/cooperation clauses, so the organization
is the part before the clause ("Cisco Networking Academy"). General-purpose;
applies to any certificate phrased "provided by X in collaboration with Y".

The OCR integration tests use the real certificate stored under
`tests/fixtures/python_essentials.pdf` so the exact image the user uploaded is
exercised end-to-end (same image -> same OCR text -> same extraction).
"""

import pathlib

import pytest

from app.services.extraction_service import _extract_issuer, extract_document
from app.services.ocr_service import is_available

_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
PYTHON_ESSENTIALS_PDF = _FIXTURES / "python_essentials.pdf"


# The OCR-derived text for the real certificate (merged PDF layer + OCR). This
# is the exact text that produced the false positive before the fix.
PYTHON_OCR_TEXT = (
    "ROHITH KUMAR K R IT\n"
    "Issued on: Jan 23, 2025\n"
    "....\n"
    "Networking\n"
    "Python\n"
    "Academy\n"
    "PI\n"
    "cisco\n"
    "INSTITUTE\n"
    "Open EducationandDevelopmentGroup\n"
    "Statement of Achievement\n"
    "ROHITH KUMAR K R IT\n"
    "has successfully achieved student level credential for completing the Python Essentials 1\n"
    "course, provided by Cisco Networking Academy in collaboration with OpenEDG Python\n"
    "Institute.\n"
    "The graduate has studied:\n"
    "Design, develop, debug, execute, and refactor simple computer programs written in Python 3.\n"
    "Think algorithmically to analyze problems and implement them as computer processes.\n"
    "Use the syntax, semantics, and the most important elements of the Python Standard Library to write Python scripts and\n"
    "resolve typical implementation challenges.\n"
    "continue their professional development at an intermediate level with Python Essentials 2.\n"
    "..l...l.. Networking\n"
    "CISCO\n"
    "Academy\n"
    "ynn Bleomer\n"
    "Verified\n"
    "Lyhn Bloomer\n"
    "Python Essentials 1\n"
    "Director, Cisco Networking Academy\n"
    "Scan to Verify\n"
    "Issued on: Jan 23, 2025\n"
)

# Clean, single-line phrasing of the same certificate (used only as reference;
# the OCR integration tests run on the real fixture PDF).
PYTHON_STYLE_TEXT = (
    "Python Institute\n"
    "Cisco Networking Academy\n"
    "Statement of Achievement\n"
    "ROHITH KUMAR K R IT\n"
    "has successfully achieved student level credential for completing the\n"
    "Python Essentials 1 course, provided by Cisco Networking Academy in\n"
    "collaboration with OpenEDG Python Institute.\n"
    "Lyhn Bloomer\n"
    "Director, Cisco Networking Academy\n"
    "Issued on: Jan 23, 2025\n"
)


# --------------------------------------------------------------------------
# Deterministic unit tests on the exact OCR text (the bug mechanism)
# --------------------------------------------------------------------------

def test_issuer_collaboration_clause_is_truncated():
    """'...provided by Cisco Networking Academy in collaboration with OpenEDG
    Python Institute.' must yield 'Cisco Networking Academy' — not a 61-char
    capture that trips the issuer length cap."""
    assert _extract_issuer(PYTHON_OCR_TEXT) == "Cisco Networking Academy"


def test_issuer_clause_split_variants():
    from app.services.extraction_service import _clean_issuer_marker

    for clause in ("collaboration", "partnership", "association", "cooperation", "conjunction"):
        capture = f"CloudForge Academy in {clause} with OpenEDG Institute"
        assert _clean_issuer_marker(capture) == "CloudForge Academy"


def test_issuer_capture_without_clause_keeps_full_name():
    from app.services.extraction_service import _clean_issuer_marker

    assert _clean_issuer_marker("University of Cambridge") == "University of Cambridge"


def test_python_ocr_text_extracts_full_fields():
    from app.services.extraction_service import extract_fields

    fields = extract_fields(PYTHON_OCR_TEXT, allow_bare_name=True)
    assert fields["candidate_name"] == "ROHITH KUMAR K R IT"
    assert fields["organization"] == "Cisco Networking Academy"
    assert fields["course"] == "Python Essentials 1"
    assert fields["issue_date"] == "2025-01-23"


# --------------------------------------------------------------------------
# OCR integration on the REAL uploaded certificate (image-heavy, tiny text
# layer) + model prediction
# --------------------------------------------------------------------------

@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_python_essentials_real_cert_extracts_issuer_via_ocr():
    result = extract_document(str(PYTHON_ESSENTIALS_PDF), "pdf")

    assert result.ocr_used is True
    assert result.extraction_method in ("ocr", "hybrid")
    assert result.fields["organization"] == "Cisco Networking Academy"
    assert result.fields["course"] == "Python Essentials 1"
    assert result.fields["candidate_name"] == "ROHITH KUMAR K R IT"
    assert result.fields["issue_date"] == "2025-01-23"


@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_python_essentials_real_cert_predicts_genuine(client):
    data = PYTHON_ESSENTIALS_PDF.read_bytes()

    resp = client.post(
        "/api/verify",
        files={
            "file": (
                "PythonEssentials1Update20250123-28-a15e7b.pdf",
                data,
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["extracted"]["organization"] == "Cisco Networking Academy"
    assert body["extracted"]["candidate_name"] == "ROHITH KUMAR K R IT"
    assert body["extracted"]["course"] == "Python Essentials 1"
    assert body["extraction"]["ocr_used"] is True
    # The issuer recovery (not any model change) flips the verdict.
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5


# --------------------------------------------------------------------------
# Fraud regression: collaboration clauses must not hide fraud issuers
# --------------------------------------------------------------------------

def test_fraud_with_collaboration_clause_stays_suspicious(client):
    from tests.conftest import _make_pdf

    fraud_text = (
        "Online Degree Emporium\n"
        "Certificate of Completion\n"
        "for successfully completing\n"
        "Python Essentials 1 course, provided by Online Degree Emporium in collaboration with\n"
        "Instant Diploma Mill\n"
        "26 Dec 2030\n"
        "Completion Date\n"
    )
    resp = client.post(
        "/api/verify",
        files={
            "file": ("fraud_collab.pdf", _make_pdf(fraud_text), "application/pdf"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extracted"]["organization"] == "Online Degree Emporium"
    assert body["prediction"] == "suspicious"
    assert body["risk_score"] > 0.5