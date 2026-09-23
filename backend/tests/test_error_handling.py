"""Tests for API error handling: missing/invalid files and model availability."""

from app.core.config import settings
from app.ml import model as model_service


def test_verify_without_file(client):
    resp = client.post("/api/verify")
    assert resp.status_code == 422


def test_verify_unsupported_extension(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("evil.exe", b"MZ\x90\x00 binary", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_verify_malformed_file(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("fake.pdf", b"this is not a real pdf", "application/pdf")},
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


def test_verify_empty_file(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert resp.status_code == 400


def test_verify_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    big = b"%PDF-1.4" + b"0" * (2 * 1024 * 1024)
    resp = client.post(
        "/api/verify",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    assert resp.status_code == 400
    assert "size limit" in resp.json()["detail"].lower()


def test_model_unavailable_on_verify(client, monkeypatch):
    monkeypatch.setattr(model_service, "is_available", lambda: False)
    resp = client.post(
        "/api/verify",
        files={"file": ("genuine.pdf", b"%PDF-1.4 ok", "application/pdf")},
    )
    assert resp.status_code == 503
    assert "detail" in resp.json()


def test_model_unavailable_on_info(client, monkeypatch):
    monkeypatch.setattr(
        model_service, "_cache", {"pipeline": None, "features": None, "metadata": None}
    )

    def fake_load():
        raise model_service.ModelUnavailableError()

    monkeypatch.setattr(model_service, "load", fake_load)
    resp = client.get("/api/model/info")
    assert resp.status_code == 503


def test_error_response_does_not_leak_traceback(monkeypatch, genuine_pdf):
    from fastapi.testclient import TestClient

    from app.main import app

    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(model_service, "is_available", lambda: True)
    monkeypatch.setattr(model_service, "predict", boom)

    # raise_server_exceptions=False so the app's 500 handler response is returned.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        resp = test_client.post(
            "/api/verify",
            files={"file": ("genuine.pdf", genuine_pdf, "application/pdf")},
        )
    assert resp.status_code == 500
    assert "secret internal detail" not in resp.text
    assert "detail" in resp.json()