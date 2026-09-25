"""Authentication and authorization tests (Clerk verification is mocked).

These tests exercise the REAL ``get_current_user`` dependency and the real
route ownership code. Only the token-verification seam
(``app.core.auth._authenticate``) is mocked; every other layer — 401/400
responses, header handling, owner-scoped queries — runs exactly as in
production. This keeps the suite hermetic (no real Clerk credentials or
network calls) without weakening the dependency wiring.
"""

from types import SimpleNamespace

import pytest

from app.core import auth as auth_module
from app.main import app
from src.data.certificate_patterns import checksum_digit
from tests.conftest import (
    TEST_USER_A,
    TEST_USER_B,
    _clear_auth_overrides,
    _install_test_auth_override,
    _make_pdf,
)

ISSUER = "https://certiguard-test.clerk.accounts.dev"
BEARER = "Bearer "


def _genuine(marker: str) -> bytes:
    """An academic-looking document whose recipient, cert id, and content are
    unique per marker, so auth tests never collide with the shared PDF fixtures
    (which would otherwise trip duplicate detection for later tests)."""
    base = "%05d" % (abs(hash(marker)) % 100000)
    cert_id = f"CERT-2021-{base}{checksum_digit(base)}"
    text = (
        "University of Cambridge\n"
        "Certificate of Achievement\n"
        "\n"
        f"We hereby certify that {marker} has completed the Data Science program.\n"
        "\n"
        "Program offered by University of Cambridge\n"
        f"Candidate ID: {cert_id}\n"
        "Marks: 88 out of 100\n"
        "Grade: B\n"
        "Issue Date: 2021-08-10\n"
        "Signature: ____________________\n"
        "Seal: University Seal\n"
        "QR code available for verification\n"
    )
    return _make_pdf(text)


def _suspicious(marker: str) -> bytes:
    """A suspicious-looking document that is unique per marker."""
    text = (
        "Online Degree Emporium\n"
        "Instant Certificate\n"
        "\n"
        "Buy verified certificates online, no exam needed.\n"
        f"Recipient: {marker}\n"
        f"Candidate ID: FREECERT-2022-{abs(hash(marker)) % 1000000}\n"
        "Marks: 150 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2026-12-01\n"
    )
    return _make_pdf(text)


def _state(signed_in: bool, payload=None, reason=None):
    return SimpleNamespace(is_signed_in=signed_in, payload=payload, reason=reason)


def _fake_authenticate(request):
    """Mirror of the real verifier's contract driven by the Authorization header."""
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return _state(False, reason="session_token_missing")
    if not header.startswith(BEARER):
        return _state(False, reason="session_token_invalid")
    token = header[len(BEARER):].strip()
    if not token:
        return _state(False, reason="session_token_invalid")
    if token in ("expired", "garbage", "forged"):
        return _state(False, reason="token_expired" if token == "expired" else "token_invalid")
    if token == "issuer-mismatch":
        return _state(True, payload={"sub": TEST_USER_A, "iss": "https://evil.example.com"})
    if token == TEST_USER_A:
        return _state(True, payload={"sub": TEST_USER_A, "iss": ISSUER, "sid": "sess_a"})
    if token == TEST_USER_B:
        return _state(True, payload={"sub": TEST_USER_B, "iss": ISSUER, "sid": "sess_b"})
    return _state(False, reason="token_invalid")


@pytest.fixture
def strict_auth(auth_override, monkeypatch):
    """Remove the test override and drive the real dependency with a mocked token verifier."""
    monkeypatch.setattr(auth_module, "_authenticate", _fake_authenticate)
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", ISSUER)
    _clear_auth_overrides()
    yield
    _install_test_auth_override()


def _verify_as(client, user_id: str, filename: str, content: bytes) -> dict:
    resp = client.post(
        "/api/verify",
        headers={"Authorization": f"{BEARER}{user_id}"},
        files={"file": (filename, content, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Public endpoints stay open
# ---------------------------------------------------------------------------

def test_public_health_and_model_info_do_not_require_auth(client, strict_auth):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    resp = client.get("/api/model/info")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Missing / malformed / incorrect tokens -> 401
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Basic dXNlcjpwYXNz"},
    {"Authorization": "Bearer "},
    {"Authorization": "Bearer expired"},
    {"Authorization": "Bearer garbage"},
])
def test_protected_endpoints_reject_bad_tokens(client, strict_auth, headers):
    resp = client.get("/api/verifications", headers=headers)
    assert resp.status_code == 401, resp.text
    assert resp.json()["detail"]


def test_token_wrong_issuer_rejected(client, strict_auth):
    resp = client.get(
        "/api/verifications",
        headers={"Authorization": "Bearer issuer-mismatch"},
    )
    assert resp.status_code == 401
    assert "Invalid session token" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# CLERK_ISSUER must be the Frontend API URL — JWKS URL stays separate
# ---------------------------------------------------------------------------

def test_frontend_api_url_normalization():
    """The issuer check compares only against the Frontend API URL.

    The Clerk Dashboard's "JWKS URL" is the Frontend API URL plus
    ``/.well-known/jwks.json``. Pasting that value into CLERK_ISSUER is the
    exact mistake that made every token fail (the `iss` claim carries the bare
    Frontend API URL). Normalization must strip the JWKS suffix, never build an
    expected issuer that contains it.
    """
    base = "https://advanced-tapir-2679.clerk.accounts.dev"
    assert auth_module._frontend_api_url(base) == base
    assert auth_module._frontend_api_url(f"{base}/") == base
    assert auth_module._frontend_api_url(f"{base}/.well-known/jwks.json") == base
    assert auth_module._frontend_api_url(f"{base}/.well-known/jwks.json/") == base
    assert auth_module._frontend_api_url(f"{base}/jwks.json") == base
    assert auth_module._frontend_api_url(None) is None
    assert auth_module._frontend_api_url("") is None


def test_jwks_url_pasted_as_issuer_still_authenticates(client, strict_auth, monkeypatch):
    """A JWKS URL in CLERK_ISSUER must not lock users out.

    Regression for the observed production failure: the configured value was
    ``https://<instance>.clerk.accounts.dev/.well-known/jwks.json`` and tokens
    carry ``iss=https://<instance>.clerk.accounts.dev``. The JWKS suffix is
    stripped before comparison, key retrieval is untouched, and a genuine token
    still authenticates.
    """
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", f"{ISSUER}/.well-known/jwks.json")
    resp = client.get(
        "/api/metrics",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    )
    assert resp.status_code == 200, resp.text


def test_jwks_url_issuer_does_not_weaken_mismatch_rejection(client, strict_auth, monkeypatch):
    """Strip JWKS suffix only strips the suffix — a foreign issuer must still fail."""
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", "https://other.example.com/.well-known/jwks.json")
    resp = client.get(
        "/api/verifications",
        headers={"Authorization": "Bearer issuer-mismatch"},
    )
    assert resp.status_code == 401


def test_jwks_url_as_issuer_is_flagged_as_misconfigured(client, strict_auth, monkeypatch, caplog):
    """The JWKS-URL-into-issuer paste mistake should be called out in the logs."""
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", f"{ISSUER}/.well-known/jwks.json")
    monkeypatch.setattr(auth_module.settings, "clerk_issuer_is_jwks_url", True)
    with caplog.at_level("WARNING", logger="auth"):
        resp = client.get(
            "/api/metrics",
            headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
        )
    assert resp.status_code == 200
    assert any("JWKS URL" in rec.message for rec in caplog.records)


def test_received_issuer_is_inspected_only_with_debug_flag(client, strict_auth, monkeypatch, caplog):
    """The received `iss` claim is surfaced ONLY when diagnostics are enabled.

    The `iss` claim is a public issuer URL (never the JWT or a secret), but it
    stays out of logs unless CLERK_DEBUG_ISSUER is on. Even then, the raw token
    must never appear in the log output.
    """
    monkeypatch.setattr(auth_module.settings, "clerk_debug_issuer", False)
    with caplog.at_level("WARNING", logger="auth"):
        client.get(
            "/api/verifications",
            headers={"Authorization": "Bearer issuer-mismatch"},
        )
    assert not any("received=" in rec.message for rec in caplog.records)

    monkeypatch.setattr(auth_module.settings, "clerk_debug_issuer", True)
    caplog.clear()
    with caplog.at_level("WARNING", logger="auth"):
        client.get(
            "/api/verifications",
            headers={"Authorization": "Bearer issuer-mismatch"},
        )
    assert any("received=https://evil.example.com" in rec.message for rec in caplog.records)
    assert not any("issuer-mismatch" in rec.message for rec in caplog.records)


def test_when_issuer_not_configured_everything_is_rejected(client, strict_auth, monkeypatch):
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", None)
    resp = client.get(
        "/api/verifications",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    )
    assert resp.status_code == 401


def test_missing_issuer_configuration_is_reported_safely(client, strict_auth, monkeypatch):
    """A server missing CLERK_ISSUER must reject with a clear but secret-free 401.

    This is the exact configuration gap that previously made the frontend
    interpret every protected request as session expiration and loop back to
    the sign-in screen. The detail must name the misconfiguration without
    leaking anything sensitive.
    """
    monkeypatch.setattr(auth_module.settings, "clerk_issuer", None)
    resp = client.get(
        "/api/verifications",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    )
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate", "").startswith("Bearer")
    detail = resp.json()["detail"]
    assert "issuer is not configured" in detail.lower()
    assert "sk_" not in detail
    assert "secret" not in detail.lower()


def test_unexpected_verifier_failure_returns_401(client, auth_override, monkeypatch):
    def _boom(request):
        raise RuntimeError("verifier exploded")

    monkeypatch.setattr(auth_module, "_authenticate", _boom)
    _clear_auth_overrides()
    try:
        resp = client.get("/api/verifications")
    finally:
        _install_test_auth_override()
    assert resp.status_code == 401


def test_unauthorized_response_carries_www_authenticate(client, strict_auth):
    resp = client.get("/api/verifications")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate", "").startswith("Bearer")


# ---------------------------------------------------------------------------
# Valid token end-to-end
# ---------------------------------------------------------------------------

def test_valid_token_can_verify_and_list(client, strict_auth):
    body = _verify_as(client, TEST_USER_A, "auth_valid.pdf", _genuine("valid"))
    assert body["verification_id"]

    rows = client.get(
        "/api/verifications",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    ).json()
    assert any(r["verification_id"] == body["verification_id"] for r in rows)


# ---------------------------------------------------------------------------
# Ownership isolation: user A's data is invisible to user B
# ---------------------------------------------------------------------------

def test_cross_user_access_is_blocked(client, strict_auth):
    body = _verify_as(client, TEST_USER_A, "auth_owner_a.pdf", _genuine("owner-a"))
    vid = body["verification_id"]

    detail = client.get(
        f"/api/verifications/{vid}",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    )
    assert detail.status_code == 400
    assert "not found" in detail.json()["detail"].lower()

    audit = client.get(
        f"/api/verifications/{vid}/audit",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    )
    assert audit.status_code == 400

    feedback = client.post(
        f"/api/verifications/{vid}/feedback",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
        json={"reviewer_label": "confirmed_genuine", "reviewer_note": "not mine"},
    )
    assert feedback.status_code == 400

    rows = client.get(
        "/api/verifications?limit=100",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    ).json()
    assert all(r["verification_id"] != vid for r in rows)

    summary = client.get(
        "/api/verifications/summary",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    ).json()
    assert summary["total"] == 0

    metrics = client.get(
        "/api/metrics",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    ).json()
    assert metrics["total_verifications"] == 0


def test_owners_can_see_their_own_resources(client, strict_auth):
    body = _verify_as(client, TEST_USER_A, "auth_self.pdf", _genuine("self"))
    vid = body["verification_id"]

    detail = client.get(
        f"/api/verifications/{vid}",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["verification_id"] == vid

    audit = client.get(
        f"/api/verifications/{vid}/audit",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    )
    assert audit.status_code == 200
    assert any(e["event_type"] == "DOCUMENT_RECEIVED" for e in audit.json()["events"])


def test_feedback_records_owner_from_token_not_payload(client, strict_auth):
    """A caller-supplied owner id in the payload must be ignored."""
    body = _verify_as(client, TEST_USER_A, "auth_owner_spoof.pdf", _genuine("spoof"))
    vid = body["verification_id"]

    resp = client.post(
        f"/api/verifications/{vid}/feedback",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
        json={
            "reviewer_label": "confirmed_suspicious",
            "reviewer_note": "mine",
            "user_id": TEST_USER_B,
            "owner": TEST_USER_B,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "error" not in str(data).lower()

    from app.database.database import SessionLocal
    from app.models.feedback import VerificationFeedback

    db = SessionLocal()
    try:
        row = db.query(VerificationFeedback).filter(
            VerificationFeedback.verification_id == vid
        ).one()
        assert row.user_id == TEST_USER_A
    finally:
        db.close()


def test_duplicate_detection_is_scoped_to_the_user(client, strict_auth):
    _verify_as(client, TEST_USER_A, "auth_dup_a.pdf", _suspicious("dup"))

    both = client.get(
        "/api/verifications?limit=100",
        headers={"Authorization": f"{BEARER}{TEST_USER_A}"},
    ).json()
    assert any(r["filename"] == "auth_dup_a.pdf" for r in both)

    others = client.get(
        "/api/verifications?limit=100",
        headers={"Authorization": f"{BEARER}{TEST_USER_B}"},
    ).json()
    assert all(r["filename"] != "auth_dup_a.pdf" for r in others)