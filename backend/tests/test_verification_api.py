"""API tests for the verification flow and database persistence."""

from app.models.certificate import Certificate
from app.models.verification import Verification


def test_verify_genuine_pdf(client, genuine_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("genuine.pdf", genuine_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    for key in ("verification_id", "prediction", "risk_score", "confidence",
                "model_version", "message", "label"):
        assert key in body, f"missing key {key}"
    assert body["prediction"] == "genuine"
    assert body["label"] == "GENUINE"
    assert body["risk_score"] < 0.5
    assert body["confidence"] > 0.5
    assert body["model_version"]
    assert body["verification_id"].startswith("V")
    assert isinstance(body["extracted"], dict)
    assert body["extracted"]["candidate_name"] == "John Walker"


def test_verify_suspicious_pdf(client, suspicious_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("suspicious.pdf", suspicious_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "suspicious"
    assert body["risk_score"] >= 0.5
    assert body["label"] == "SUSPICIOUS"
    assert "manual review" in body["message"].lower()


def test_verify_persists_certificate_and_verification(client, db_session, genuine_pdf):
    before_verifications = db_session.query(Verification).count()
    before_certificates = db_session.query(Certificate).count()

    resp = client.post(
        "/api/verify",
        files={"file": ("persist.pdf", genuine_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert db_session.query(Verification).count() == before_verifications + 1
    assert db_session.query(Certificate).count() == before_certificates + 1

    record = (
        db_session.query(Verification)
        .filter(Verification.verification_id == body["verification_id"])
        .one()
    )
    assert record.filename == "persist.pdf"
    assert record.prediction == body["prediction"]
    assert record.risk_score == body["risk_score"]
    assert record.confidence == body["confidence"]
    assert record.model_version == body["model_version"]

    cert = db_session.get(Certificate, record.certificate_id)
    assert cert is not None
    assert cert.original_filename == "persist.pdf"
    assert cert.status == body["prediction"]
    assert cert.confidence == body["confidence"]
    assert cert.file_path and cert.file_path.strip()


def test_verifications_endpoint(client):
    resp = client.get("/api/verifications")
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    for item in items:
        assert "verification_id" in item
        assert "prediction" in item


def test_metrics_endpoint(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["total_verifications"], int)
    assert "prediction_distribution" in body
    assert "model_versions" in body
    assert isinstance(body["recent"], list)


def test_metrics_include_counts_and_certificate_types(client, genuine_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("genuine_m.pdf", genuine_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["certificate_type"]  # academic/completion/training/technical flags

    metrics = client.get("/api/metrics").json()
    assert isinstance(metrics["genuine_count"], int)
    assert isinstance(metrics["suspicious_count"], int)
    assert isinstance(metrics["error_count"], int)
    assert isinstance(metrics["certificate_type_distribution"], dict)
    assert metrics["genuine_count"] >= 1
    assert metrics["total_verifications"] >= 1


def test_verify_multiple_uploads_rejected(client, genuine_pdf):
    resp = client.post(
        "/api/verify",
        files=[
            ("file", ("one.pdf", genuine_pdf, "application/pdf")),
            ("file", ("two.pdf", genuine_pdf, "application/pdf")),
        ],
    )
    assert resp.status_code == 400


def test_verifications_limit_bounds(client):
    assert client.get("/api/verifications?limit=0").status_code == 422
    assert client.get("/api/verifications?limit=101").status_code == 422
    resp = client.get("/api/verifications?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) <= 5


def test_verify_response_contains_explanation(client, genuine_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("explain.pdf", genuine_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "explanation" in body
    assert isinstance(body["explanation"], list)
    assert len(body["explanation"]) >= 1
    signal = body["explanation"][0]
    for key in ("key", "label", "status", "detail"):
        assert key in signal


def test_verifications_search_and_filter(client, genuine_pdf, suspicious_pdf):
    client.post(
        "/api/verify",
        files={"file": ("alpha_search.pdf", genuine_pdf, "application/pdf")},
    )
    client.post(
        "/api/verify",
        files={"file": ("beta_suspicious.pdf", suspicious_pdf, "application/pdf")},
    )

    hit = client.get("/api/verifications?search=alpha_search&limit=100").json()
    assert len(hit) == 1
    assert hit[0]["filename"] == "alpha_search.pdf"

    gen = client.get("/api/verifications?prediction=genuine&limit=100").json()
    assert all(r["prediction"] == "genuine" for r in gen)

    sus = client.get("/api/verifications?prediction=suspicious&limit=100").json()
    assert all(r["prediction"] == "suspicious" for r in sus)

    newest = client.get("/api/verifications?sort=newest&limit=100").json()
    oldest = client.get("/api/verifications?sort=oldest&limit=100").json()
    assert newest[0]["verification_id"] != oldest[0]["verification_id"]

    assert client.get("/api/verifications?sort=bogus").status_code == 422


def test_verifications_certificate_type_filter(client, genuine_pdf):
    client.post(
        "/api/verify",
        files={"file": ("ct_filter.pdf", genuine_pdf, "application/pdf")},
    )
    academic = client.get("/api/verifications?certificate_type=academic&limit=100").json()
    technical = client.get("/api/verifications?certificate_type=technical&limit=100").json()
    academic_ids = {r["verification_id"] for r in academic}
    technical_ids = {r["verification_id"] for r in technical}
    # The genuine University-of-Cambridge PDF is academic and NOT technical.
    assert any(r["filename"] == "ct_filter.pdf" for r in academic)
    assert all(r["verification_id"] not in academic_ids for r in technical)