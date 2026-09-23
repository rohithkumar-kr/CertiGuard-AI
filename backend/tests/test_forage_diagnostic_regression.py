"""Forage certificate diagnostic regression test (read-only diagnostic).

Runs the actual uploaded Forage certificate
(``backend/uploads/aec1482873104bafb0930e7c8a3ef3bb.pdf``) through the full
production pipeline and FREEZES the CURRENT result so the behavior cannot
change silently while the diagnostic investigation is open.

This is NOT an assertion that the certificate must be VERIFIED. It captures the
measured current outcome only.

Current measured result (2026-08-20):
  prediction = genuine (risk 0.2075, threshold 0.5)
  decision   = REQUIRES_VERIFICATION (verification codes could not be confirmed
               against the issuer -> VERIFICATION_UNAVAILABLE)
"""

from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent

FORAGE_PDF = _BACKEND / "uploads" / "aec1482873104bafb0930e7c8a3ef3bb.pdf"

pytestmark = pytest.mark.regression


@pytest.mark.skipif(not FORAGE_PDF.exists(), reason="forage fixture not present")
def test_forage_certificate_current_result_is_frozen(client):
    with open(FORAGE_PDF, "rb") as fh:
        data = fh.read()
    resp = client.post(
        "/api/verify",
        files={"file": ("forage inttroduction to software engineeringjob simulation(1).pdf", data, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()

    # --- Extraction: the upgraded extractor must recover the full identity ---
    assert body["extracted"]["candidate_name"] == "Rohith Kumar K R"
    assert body["extracted"]["issue_date"] == "2026-03-30"
    assert "Introduction to Software Engineering Job Simulation" in body["extracted"]["course"]
    assert body["extracted"]["organization"] == "Forage"
    codes = body["extracted"]["verification_codes"]
    assert len(codes) == 2
    assert {c["code"] for c in codes} == {"sJLRwfFRRwiZ6mSZk", "69c683a40afbea3f2d948ab3"}

    # --- ML: current measured result is genuine, below the 0.5 threshold ---
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5

    # --- Evidence engine: current decision is REQUIRES_VERIFICATION ---
    ve = body["verification_evidence"]
    assert ve["decision"] == "REQUIRES_VERIFICATION"
    assert ve["assessment"] == "REQUIRES_VERIFICATION"
    assert ve["next_action"] == "manual_verification"
    # The verification codes could not be confirmed against the issuer.
    summary = ve.get("summary") or {}
    assert summary.get("verification_codes_state") == "VERIFICATION_UNAVAILABLE"

    # Issuer is identified in the registry but not independently verified.
    issuer_items = [it for it in ve.get("evidence_items", []) if it["category"] == "ISSUER"]
    assert issuer_items and issuer_items[0]["status"] == "WARNING"

    # --- No independent negative evidence pushes this toward SUSPICIOUS ---
    assert summary.get("negative_mass") == 0.0
    assert summary.get("ml_suspicious") is False
    assert summary.get("strong_tampering") is False
    for item in ve.get("evidence_items", []):
        assert item["status"] != "FAIL", f"unexpected FAIL evidence: {item}"

    # --- Forensics show no anomalies ---
    forensic_items = [it for it in ve.get("evidence_items", []) if it["category"] == "FORENSICS"]
    assert forensic_items and forensic_items[0]["status"] == "PASS"

    # --- Issuer verification block (issuer verification layer) ---
    iv = body.get("issuer_verification") or {}
    assert iv.get("status") == "VERIFICATION_UNAVAILABLE"
    assert not iv.get("is_verified")
    assert iv.get("issuer") == "Forage"
    assert iv.get("source") == "issuer_registry"
    # Identifiers are masked in the API response, never exposed raw.
    assert all("****" in str(c) for c in (iv.get("checked_identifiers") or []))
    assert any(str(c) not in {c_["code"] for c_ in codes} for c in (iv.get("checked_identifiers") or []))
    # Honest reason: no fabrication, no invented endpoint.
    assert "NOT evidence of fraud" in (iv.get("reason") or "")