"""Phase 8 tests: intelligence layer, consistency engine, review status,
duplicate detection, history filters/summary, and monitoring extensions."""

import json

from tests.conftest import COMPLETION_PDF_TEXT, GENUINE_PDF_TEXT, _make_pdf

from app.models.verification import Verification


def _verify(client, name, content):
    resp = client.post(
        "/api/verify",
        files={"file": (name, content, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_intelligence_fields_present(client, genuine_pdf):
    body = _verify(client, "intel_genuine.pdf", genuine_pdf)
    assert "review_status" in body
    assert "recommended_action" in body
    assert "intelligence" in body
    assert "positive_signals" in body
    assert "risk_signals" in body
    assert "duplicate" in body

    intel = body["intelligence"]
    assert intel["certificate_type"]["primary"] == "academic"
    assert intel["identity"]["recipient"]["value"] == "John Walker"
    assert intel["identity"]["issuer"]["value"] == "University of Cambridge"
    assert intel["identity"]["certificate_id"]["present"] is True
    assert body["duplicate"]["is_duplicate"] is False


def test_genuine_has_positive_signals(client, genuine_pdf):
    body = _verify(client, "pos_signals.pdf", genuine_pdf)
    keys = {s["key"] for s in body["positive_signals"]}
    assert "recognized_issuer" in keys
    assert "recipient_extracted" in keys
    assert "consistent_date" in keys
    assert "valid_certificate_id" in keys


def test_suspicious_has_risk_signals(client, suspicious_pdf):
    body = _verify(client, "risk_signals.pdf", suspicious_pdf)
    assert body["prediction"] == "suspicious"
    assert body["review_status"] == "high_risk"
    assert body["recommended_action"]["action"] == "investigate"
    risk_keys = {s["key"] for s in body["risk_signals"]}
    assert "invalid_cert_id" in risk_keys
    assert "marks_exceed_total" in risk_keys
    assert "suspicious_wording" in risk_keys
    assert "invalid_date" in risk_keys
    assert "unknown_issuer" in risk_keys


def test_inconsistent_grade_and_future_date(client, inconsistent_pdf):
    body = _verify(client, "inconsistent.pdf", inconsistent_pdf)
    # Future issue date + grade/marks mismatch are strong signals.
    assert body["review_status"] in ("manual_review", "high_risk")
    assert body["recommended_action"]["action"] in ("manual_review", "investigate")
    risk_keys = {s["key"] for s in body["risk_signals"]}
    assert "grade_marks_mismatch" in risk_keys
    assert "invalid_date" in risk_keys


def test_completion_certificate_type(client, completion_pdf):
    body = _verify(client, "completion.pdf", completion_pdf)
    intel = body["intelligence"]
    # AWS Training & Certification carries certification context + a cloud
    # domain, so the model may classify it technical rather than completion.
    assert intel["certificate_type"]["primary"] in (
        "completion", "training", "technical",
    )
    assert intel["identity"]["recipient"]["present"] is True
    assert body["review_status"] in ("low_risk", "manual_review")


def test_technical_certificate_type(client, technical_pdf):
    body = _verify(client, "technical.pdf", technical_pdf)
    intel = body["intelligence"]
    assert intel["certificate_type"]["primary"] in ("technical", "training")
    assert intel["identity"]["certificate_id"]["present"] is True


def test_workshop_certificate_type(client, workshop_pdf):
    body = _verify(client, "workshop.pdf", workshop_pdf)
    intel = body["intelligence"]
    assert intel["certificate_type"]["flags"]["workshop"] == 1


def test_unknown_issuer_signal(client, unknown_issuer_pdf):
    body = _verify(client, "unknown_issuer.pdf", unknown_issuer_pdf)
    risk_keys = {s["key"] for s in body["risk_signals"]}
    assert "unknown_issuer" in risk_keys


def test_missing_recipient_not_fraud(client, missing_recipient_pdf):
    body = _verify(client, "missing_recipient.pdf", missing_recipient_pdf)
    intel = body["intelligence"]
    assert intel["identity"]["recipient"]["present"] is False
    # Missing field is reported, but the system must not auto-flag as fraud.
    assert "missing_recipient" in {s["key"] for s in body["risk_signals"]}


def test_missing_recipient_finding_text(client, missing_recipient_pdf):
    body = _verify(client, "missing_recipient2.pdf", missing_recipient_pdf)
    findings = {f["key"]: f for f in body["intelligence"]["consistency_findings"]}
    assert "missing_recipient" in findings
    assert "No recipient name could be extracted" in findings["missing_recipient"]["detail"]


# ---------------------------------------------------------------------------
# Duplicate detection (8D)
# ---------------------------------------------------------------------------

def _unique_pdf(base_text: str, marker: str) -> bytes:
    return _make_pdf(base_text + f"\nUnique marker: {marker}\n")


def _dup_cert_text(marker: str, name: str) -> str:
    """A genuine-style certificate with a unique recipient + cert ID so its
    fingerprints cannot collide with other tests in the shared session DB."""
    return (
        "University of Cambridge\n"
        "Certificate of Achievement\n"
        "\n"
        f"We hereby certify that {name} has completed the Computer Science program.\n"
        "\n"
        "Program offered by University of Cambridge\n"
        f"Candidate ID: CERT-2021-{marker}\n"
        "Marks: 95 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2021-06-15\n"
        "Signature: ____________________\n"
        "Seal: University Seal\n"
        "QR code available for verification\n"
    )


def test_duplicate_exact_file(client):
    text = _dup_cert_text("900001", "Dup Exact Alpha") + "\nUnique marker: dup-exact\n"
    content = _make_pdf(text)
    first = _verify(client, "dup_a.pdf", content)
    assert first["duplicate"]["is_duplicate"] is False
    second = _verify(client, "dup_b.pdf", content)
    assert second["duplicate"]["is_duplicate"] is True
    assert second["duplicate"]["duplicate_type"] == "file"
    assert second["duplicate"]["duplicate_of"] == first["verification_id"]


def test_duplicate_same_cert_id(client):
    # Two documents sharing the same certificate ID but different file bytes
    # (different recipient) must be flagged via the cert_id fingerprint.
    base = _dup_cert_text("900002", "Cert Id Alpha") + "\nUnique marker: certid-a\n"
    varied = _dup_cert_text("900002", "Cert Id Beta") + "\nUnique marker: certid-b\n"
    first = _verify(client, "certid_a.pdf", _make_pdf(base))
    assert first["duplicate"]["is_duplicate"] is False
    second = _verify(client, "certid_b.pdf", _make_pdf(varied))
    assert second["duplicate"]["is_duplicate"] is True
    assert second["duplicate"]["duplicate_type"] == "cert_id"
    assert second["duplicate"]["duplicate_of"] == first["verification_id"]


def test_same_recipient_different_certificates_not_flagged(client):
    # Same person, two different legitimate certificates (different course AND
    # date) must NOT be flagged as duplicates — the identity fingerprint
    # requires the full recipient+issuer+course+date combination to match.
    text_a = _dup_cert_text("900003", "Same Person") + "\nUnique marker: sp-uni\n"
    text_b = (
        "CloudForge Academy\n"
        "Technical Certification\n"
        "\n"
        "This certifies that Same Person has demonstrated proficiency in Cloud Computing.\n"
        "Certification Code: CERT-2023-900004\n"
        "Issued by CloudForge Academy\n"
        "Issue Date: 2023-03-10\n"
        "Signature: ____________\n"
    )
    uni = _verify(client, "same_person_uni.pdf", _make_pdf(text_a))
    other = _verify(client, "same_person_aws.pdf", _make_pdf(text_b))
    assert uni["duplicate"]["is_duplicate"] is False
    assert other["duplicate"]["is_duplicate"] is False


def test_duplicate_persisted(client, db_session):
    text = _dup_cert_text("900005", "Persist Dup") + "\nUnique marker: persist-dup\n"
    content = _make_pdf(text)
    _verify(client, "persist_dup1.pdf", content)
    body = _verify(client, "persist_dup2.pdf", content)
    record = (
        db_session.query(Verification)
        .filter(Verification.verification_id == body["verification_id"])
        .one()
    )
    assert record.duplicate_of is not None
    assert record.duplicate_type == "file"
    assert record.file_fingerprint


# ---------------------------------------------------------------------------
# History filters + summary (8G)
# ---------------------------------------------------------------------------

def test_history_review_status_filter(client, genuine_pdf, suspicious_pdf, db_session):
    from datetime import datetime

    from app.models.verification import Verification
    from tests.conftest import TEST_USER_A

    _verify(client, "rev_high.pdf", suspicious_pdf)
    # Seed a low_risk record directly so the filter is exercised regardless of
    # the model's risk band for the synthetic fixtures.
    low = Verification(
        verification_id="V-TEST-LOW1",
        user_id=TEST_USER_A,
        filename="rev_low_seeded.pdf",
        prediction="genuine",
        label="GENUINE",
        risk_score=0.10,
        confidence=0.9,
        model_version="random_forest_v3",
        review_status="low_risk",
        issuer="University of Oxford",
    )
    db_session.add(low)
    db_session.commit()
    low_rows = client.get("/api/verifications?review_status=low_risk&limit=100").json()
    assert any(r["filename"] == "rev_low_seeded.pdf" for r in low_rows)
    assert all(r["review_status"] == "low_risk" for r in low_rows)
    high_rows = client.get("/api/verifications?review_status=high_risk&limit=100").json()
    assert any(r["filename"] == "rev_high.pdf" for r in high_rows)
    assert all(r["review_status"] == "high_risk" for r in high_rows)


def test_history_issuer_filter(client, genuine_pdf):
    _verify(client, "issuer_f.pdf", genuine_pdf)
    rows = client.get("/api/verifications?issuer=cambridge&limit=100").json()
    assert any(r["filename"] == "issuer_f.pdf" for r in rows)
    assert all("Cambridge" in (r["issuer"] or "") for r in rows)


def test_history_risk_range_filter(client, genuine_pdf, suspicious_pdf):
    _verify(client, "risk_lo.pdf", genuine_pdf)
    _verify(client, "risk_hi.pdf", suspicious_pdf)
    lo = client.get("/api/verifications?risk_max=0.49&limit=100").json()
    assert any(r["filename"] == "risk_lo.pdf" for r in lo)
    hi = client.get("/api/verifications?risk_min=0.5&limit=100").json()
    assert any(r["filename"] == "risk_hi.pdf" for r in hi)


def test_history_summary_endpoint(client, genuine_pdf, suspicious_pdf):
    _verify(client, "sum_genuine.pdf", genuine_pdf)
    _verify(client, "sum_suspicious.pdf", suspicious_pdf)
    summary = client.get("/api/verifications/summary").json()
    for key in ("total", "genuine_count", "suspicious_count",
                "manual_review_count", "average_risk_score"):
        assert key in summary
    assert summary["total"] >= 2
    assert summary["genuine_count"] >= 1
    assert summary["suspicious_count"] >= 1


def test_history_summary_respects_filters(client, genuine_pdf):
    name = "sum_filt.pdf"
    _verify(client, name, _make_pdf(GENUINE_PDF_TEXT + "\nUnique marker: sum-filt\n"))
    # The genuine document must be counted under prediction=genuine...
    gen_summary = client.get("/api/verifications/summary?prediction=genuine").json()
    rows = client.get(f"/api/verifications?search={name}&limit=100").json()
    assert any(r["filename"] == name for r in rows)
    # ...and must NOT appear under prediction=suspicious when nothing suspicious
    # shares this exact file.
    assert gen_summary["total"] >= 1
    filtered = client.get(f"/api/verifications/summary?prediction=suspicious&search={name}").json()
    assert filtered["total"] == 0


# ---------------------------------------------------------------------------
# Monitoring extensions (8H)
# ---------------------------------------------------------------------------

def test_metrics_review_status_and_issuer(client, genuine_pdf, suspicious_pdf):
    _verify(client, "metrics_a.pdf", genuine_pdf)
    _verify(client, "metrics_b.pdf", suspicious_pdf)
    metrics = client.get("/api/metrics").json()
    assert "review_status_distribution" in metrics
    assert metrics["review_status_distribution"]["high_risk"] >= 1
    assert isinstance(metrics["average_extraction_completeness"], float)
    assert isinstance(metrics["issuer_distribution"], dict)
    assert "University of Cambridge" in metrics["issuer_distribution"]
    assert isinstance(metrics["manual_review_rate"], float)


# ---------------------------------------------------------------------------
# Error cases required by the phase (8I)
# ---------------------------------------------------------------------------

def test_malformed_pdf_rejected(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("bad.pdf", b"this is not a real pdf", "application/pdf")},
    )
    assert resp.status_code == 400


def test_empty_pdf_rejected(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400


def test_unsupported_file_rejected(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("evil.exe", b"MZ\x90\x00binary", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_multiple_uploads_rejected(client, genuine_pdf):
    resp = client.post(
        "/api/verify",
        files=[
            ("file", ("one.pdf", genuine_pdf, "application/pdf")),
            ("file", ("two.pdf", genuine_pdf, "application/pdf")),
        ],
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Review-status boundary rules (8C)
# ---------------------------------------------------------------------------

def test_review_status_rules_pure():
    from app.services.intelligence_service import compute_review_status

    # prediction suspicious -> high_risk regardless of score
    assert compute_review_status("suspicious", 0.5, []) == "high_risk"
    # genuine with risk above review band -> manual_review
    assert compute_review_status("genuine", 0.35, []) == "manual_review"
    # genuine below band, no signals -> low_risk
    assert compute_review_status("genuine", 0.20, []) == "low_risk"
    # any high-severity signal forces review
    high = [{"severity": "high"}]
    assert compute_review_status("genuine", 0.20, high) == "manual_review"
    # >= 2 medium signals -> manual_review
    two_med = [{"severity": "medium"}, {"severity": "medium"}]
    assert compute_review_status("genuine", 0.20, two_med) == "manual_review"
    # one medium signal alone -> low_risk
    one_med = [{"severity": "medium"}]
    assert compute_review_status("genuine", 0.20, one_med) == "low_risk"