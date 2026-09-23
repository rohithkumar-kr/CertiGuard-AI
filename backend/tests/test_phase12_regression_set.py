"""Phase 12 known-difficult regression set (M12).

Runs the documents that previously produced false positives / were hard for
the system through the full verification pipeline and locks their expected
outcome. These are regression fixtures, NOT exceptions: the same generic rules
apply to them as to any other document.

Cases:
  1. Introduction to Modern AI  (image-heavy, OCR recovery)  -> genuine
  2. CCNA certificate           (generic course phrase)      -> genuine
  3. Python Essentials 1        (issuer collaboration clause)-> genuine
  4. Genuine AWS completion     (real uploaded cert)         -> genuine
  5. Inconsistent sample        (future date + grade clash)  -> not genuine
  6. Known fraud certificates                                  -> suspicious

All tests go through the public API (full pipeline), so duplicates, evidence
fusion, forensics, etc. are exercised too.
"""

import os
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent

INTRO_AI_PDF = _BACKEND / "uploads" / "7db3d8127651442888419df4aa6567da.pdf"
CCNA_PDF = _BACKEND / "uploads" / "2c857804dcbd498bb83e5517815ed206.pdf"
PYTHON_PDF = _BACKEND / "tests" / "fixtures" / "python_essentials.pdf"
AWS_PDF = _BACKEND / "external_validation" / "completion" / "aws_completion_certificate.pdf"
INCONSISTENT_PDF = _BACKEND / "external_validation" / "academic" / "project_sample_inconsistent.pdf"

FRAUD_PDFS = [
    _BACKEND / "external_validation" / "academic" / "fraud_degree_mill.pdf",
    _BACKEND / "external_validation" / "completion" / "fraud_instant_cert.pdf",
    _BACKEND / "external_validation" / "technical" / "fraud_for_sale.pdf",
    _BACKEND / "external_validation" / "training" / "fraud_pay_now.pdf",
]

pytestmark = pytest.mark.regression


def _post(client, path: Path, name: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    resp = client.post(
        "/api/verify",
        files={"file": (name, data, "application/pdf")},
    )
    assert resp.status_code == 200, f"verify failed for {name}: {resp.text[:500]}"
    return resp.json()


def _assert_evident_verdict(body: dict, expected: str) -> None:
    """Assert on the prediction and, when present, the final assessment."""
    assert body["prediction"] == expected
    ve = body.get("verification_evidence") or {}
    if ve:
        assert ve["assessment"] in (
            "LIKELY_GENUINE",
            "LIKELY_SUSPICIOUS",
            "REQUIRES_VERIFICATION",
            "INSUFFICIENT_EVIDENCE",
        )
        assert ve["evidence_items"], "evidence items must be present"


def _assert_genuine(body: dict) -> None:
    """A genuine cert must never be LIKELY_SUSPICIOUS; if the shared test DB
    already contains a document with the same identity fingerprint (other test
    modules verify synthetic versions of these real certs), the final
    assessment may legitimately be REQUIRES_VERIFICATION due to the duplicate
    signal. In a clean DB it must be LIKELY_GENUINE."""
    assert body["prediction"] == "genuine"
    ve = body["verification_evidence"]
    assert ve["assessment"] in ("LIKELY_GENUINE", "REQUIRES_VERIFICATION")
    if ve["assessment"] == "LIKELY_GENUINE":
        return
    dup = body.get("duplicate") or {}
    assert dup.get("is_duplicate") is True, (
        "REQUIRES_VERIFICATION without a duplicate is unexpected for a clean "
        "genuine certificate"
    )


@pytest.mark.skipif(not INTRO_AI_PDF.exists(), reason="intro-to-ai fixture not present")
def test_introduction_to_modern_ai_stays_genuine(client):
    body = _post(client, INTRO_AI_PDF, "introduction_to_modern_ai.pdf")
    assert body["risk_score"] < 0.5
    _assert_genuine(body)


@pytest.mark.skipif(not CCNA_PDF.exists(), reason="ccna fixture not present")
def test_ccna_stays_genuine(client):
    body = _post(client, CCNA_PDF, "ccna.pdf")
    assert body["risk_score"] < 0.5
    _assert_genuine(body)


@pytest.mark.skipif(not PYTHON_PDF.exists(), reason="python essentials fixture not present")
def test_python_essentials_stays_genuine(client):
    body = _post(client, PYTHON_PDF, "python_essentials.pdf")
    assert body["risk_score"] < 0.5
    _assert_genuine(body)


@pytest.mark.skipif(not AWS_PDF.exists(), reason="aws fixture not present")
def test_genuine_aws_stays_genuine(client):
    body = _post(client, AWS_PDF, "aws_completion_certificate.pdf")
    assert body["risk_score"] < 0.5
    _assert_genuine(body)


@pytest.mark.skipif(not INCONSISTENT_PDF.exists(), reason="inconsistent fixture not present")
def test_inconsistent_sample_is_never_accepted(client):
    body = _post(client, INCONSISTENT_PDF, "project_sample_inconsistent.pdf")
    ve = body.get("verification_evidence") or {}
    # A document with a future date and grade/marks contradiction must never be
    # assessed as LIKELY_GENUINE.
    assert ve.get("assessment") != "LIKELY_GENUINE"
    assert ve.get("assessment") in ("LIKELY_SUSPICIOUS", "REQUIRES_VERIFICATION")


@pytest.mark.parametrize("pdf_path", [str(p) for p in FRAUD_PDFS],
                         ids=[p.name for p in FRAUD_PDFS])
@pytest.mark.skipif(not any(p.exists() for p in FRAUD_PDFS), reason="fraud fixtures not present")
def test_fraud_certificates_remain_suspicious(client, pdf_path):
    path = Path(pdf_path)
    if not path.exists():
        pytest.skip(f"fixture not present: {path.name}")
    body = _post(client, path, path.name)
    assert body["risk_score"] >= 0.5
    _assert_evident_verdict(body, "suspicious")
    ve = body["verification_evidence"]
    assert ve["assessment"] in ("LIKELY_SUSPICIOUS", "REQUIRES_VERIFICATION")


def test_evidence_block_shape(client):
    """A normal upload returns a well-formed verification_evidence block.

    Uses a unique synthetic document so it never collides with the shared
    fixtures used by other modules (which would trip duplicate detection).
    """
    from tests.conftest import _make_pdf

    unique_text = (
        "Nova Institute of Science\n"
        "Certificate of Completion\n"
        "\n"
        "We hereby certify that Elias Vance has completed the Quantum Computing program.\n"
        "\n"
        "Offered by Nova Institute of Science\n"
        "Candidate ID: CERT-2025-555510\n"
        "Marks: 90 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2025-03-11\n"
        "Signature: ____________\n"
    )
    content = _make_pdf(unique_text)
    resp = client.post(
        "/api/verify",
        files={"file": ("evidence_shape.pdf", content, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    ve = body.get("verification_evidence")
    assert ve is not None
    assert ve["assessment"] in (
        "LIKELY_GENUINE",
        "LIKELY_SUSPICIOUS",
        "REQUIRES_VERIFICATION",
        "INSUFFICIENT_EVIDENCE",
    )
    assert "confidence" in ve
    assert "recommended_action" in ve
    assert "category_status" in ve
    assert isinstance(ve["evidence_items"], list) and len(ve["evidence_items"]) > 0
    # The ML prediction field is preserved unchanged (additive design).
    assert body["prediction"] in ("genuine", "suspicious")