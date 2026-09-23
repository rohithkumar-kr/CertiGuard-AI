"""Tests for health/home endpoints."""

from app.core.config import settings


def test_home(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == settings.app_name


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == settings.app_name
    assert body["model_loaded"] is True
    assert isinstance(body["model_version"], str) and body["model_version"]