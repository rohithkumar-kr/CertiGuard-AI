"""Clerk authentication for protected API routes.

Verifies the browser's Clerk session token on the backend using the official
``clerk-backend-api`` SDK (``authenticate_request``). Verification is fully
networkless when ``CLERK_JWT_KEY`` is set; otherwise the SDK fetches and caches
the signing JWKS from the Clerk Backend API using ``CLERK_SECRET_KEY``.

Two concerns are deliberately kept separate (the Clerk Dashboard shows them as
separate fields, and conflating them is what broke auth):

* ``CLERK_ISSUER`` is used ONLY for the token's ``iss`` claim check below. It
  must be the instance's **Frontend API URL** (e.g.
  ``https://<instance>.clerk.accounts.dev``). The Dashboard's "JWKS URL"
  (Frontend API URL + ``/.well-known/jwks.json``) is a key-fetch endpoint,
  never an issuer, so any such suffix is stripped before comparing.
* JWKS key retrieval is handled entirely by the SDK and is keyed off the
  **Backend API URL** (``https://api.clerk.com``) plus ``CLERK_SECRET_KEY``;
  it never reads ``CLERK_ISSUER``. The installed SDK builds
  ``<api_url>/<api_version>/jwks`` = ``https://api.clerk.com/v1/jwks``.

The SDK validates signature (RS256), expiry, iat/nbf leeway, audience, and azp
(authorized parties) but deliberately does NOT validate the issuer
(``verify_iss=False``); that check is performed here. Every failed verification
returns HTTP 401 and never degrades to "allow".

Nothing secret is ever logged. The only received token data surfaced for
diagnostics is the ``iss`` claim (a public issuer URL), and only when
``CLERK_DEBUG_ISSUER=1`` is set. The user id (``sub`` claim) is translated into
the owner value stored on domain rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status
from clerk_backend_api import authenticate_request, AuthenticateRequestOptions

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("auth")

# Reason strings the SDK surfaces for a rejected session token. Kept as plain
# strings so the dependency stays decoupled from SDK enum internals.
TOKEN_ERROR_HINTS = {
    "session_token_missing": "Missing session token",
    "session_token_invalid": "Invalid session token",
    "session_token_expired": "Session token expired",
    "token_expired": "Session token expired",
    "token_invalid": "Invalid session token",
    "token_incorrect_audience": "Session token audience mismatch",
    "token_nesisive_parties": "Session token authorized-party mismatch",
    "jwk_failed_to_load": "Unable to load signing key",
    "key_read_error": "Unable to read signing key",
    "secret_key_missing": "Signing key not configured",
    "token_not_active_yet": "Session token not active yet",
}


@dataclass(frozen=True)
class AuthenticatedUser:
    """The verified identity of the caller, derived only from the token."""

    id: str  # Clerk user id (the token's `sub` claim); used as row-level owner.
    session_id: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    claims: dict = field(default_factory=dict)


def _normalize_issuer(issuer: str) -> str:
    """Normalize an issuer URL for comparison (trailing-slash insensitive)."""
    return issuer.rstrip("/")


def _frontend_api_url(raw: str | None) -> str | None:
    """The bare Clerk Frontend API URL carried by a session token's ``iss`` claim.

    ``CLERK_ISSUER`` may be pasted from the Clerk Dashboard's "JWKS URL" field,
    which appends ``/.well-known/jwks.json`` to the Frontend API URL. That
    suffix is a key-fetch path and must never be compared against ``iss``.
    Strip it (plus any trailing slash) so a mis-pasted value still resolves to
    the exact issuer the tokens actually carry.
    """
    if not raw:
        return None
    value = str(raw).strip().rstrip("/")
    for suffix in ("/.well-known/jwks.json", "/jwks.json", "/.well-known/jwks"):
        if value.lower().endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")
            break
    return value or None


def _auth_error(reason: str | None) -> HTTPException:
    hint = TOKEN_ERROR_HINTS.get((reason or "").lower(), "Authentication required")
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=hint,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _build_auth_options() -> AuthenticateRequestOptions:
    return AuthenticateRequestOptions(
        secret_key=settings.clerk_secret_key,
        jwt_key=settings.clerk_jwt_key,
        authorized_parties=settings.clerk_authorized_parties,
        audience=settings.clerk_audience,
        accepts_token=["session_token"],
        clock_skew_in_ms=settings.clerk_clock_skew_ms,
    )


def _authenticate(request: Request):
    """Verify the session token carried by the request.

    Separated from the dependency so tests can mock only this seam while
    exercising the real request/response flow.
    """
    return authenticate_request(request, _build_auth_options())


def _validate_issuer(payload: dict) -> None:
    """Enforce that the token was issued by our Clerk instance.

    The expected value is the Clerk **Frontend API URL** only; a JWKS URL
    pasted into ``CLERK_ISSUER`` is stripped down to that base by
    ``_frontend_api_url``, keeping key retrieval separate from issuer checks.
    """
    expected = _frontend_api_url(settings.clerk_issuer)
    if not expected:
        logger.warning(
            "CLERK_ISSUER is not configured; all protected requests are being "
            "rejected. Set CLERK_ISSUER to your Clerk Frontend API URL "
            "(e.g. https://<your-instance>.clerk.accounts.dev) — not the JWKS URL."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication unavailable: the server's Clerk issuer is not configured.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if getattr(settings, "clerk_issuer_is_jwks_url", False):
        logger.warning(
            "CLERK_ISSUER has been set to your Clerk JWKS URL "
            "(https://<instance>.clerk.accounts.dev/.well-known/jwks.json). The "
            "issuer check must compare against the Frontend API URL only, so the "
            "JWKS suffix is being ignored. Set CLERK_ISSUER to the Frontend API "
            "URL (e.g. https://<instance>.clerk.accounts.dev)."
        )
    actual = payload.get("iss")
    if actual is None or _normalize_issuer(str(actual)) != _normalize_issuer(expected):
        # The `iss` claim is a public issuer URL, never the JWT or a secret;
        # still, only surface it when developer diagnostics are enabled.
        if settings.clerk_debug_issuer:
            logger.warning(
                "Rejecting token with unexpected issuer (expected=%s received=%s)",
                expected,
                actual,
            )
        else:
            logger.warning("Rejecting token with unexpected issuer (expected=%s)", expected)
        raise _auth_error("token_invalid")


def _validate_sub(payload: dict) -> str:
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str) or not sub.strip():
        logger.warning("Rejecting token without a user id (sub)")
        raise _auth_error("token_invalid")
    return sub.strip()


def _user_from_payload(payload: dict) -> AuthenticatedUser:
    sub = _validate_sub(payload)
    return AuthenticatedUser(
        id=sub,
        session_id=payload.get("sid") or None,
        email=payload.get("email") or None,
        first_name=payload.get("first_name") or None,
        last_name=payload.get("last_name") or None,
        claims=payload,
    )


def get_current_user(request: Request) -> AuthenticatedUser:
    """FastAPI dependency: require a valid, correctly-issued Clerk session token.

    Applies to every non-public route. Any verification failure results in a
    401; a valid session token that fails issuer/claim checks is rejected the
    same way. There is no fallback that allows unauthenticated access.
    """
    try:
        state = _authenticate(request)
    except Exception as exc:  # noqa: BLE001 - treat unexpected verifier errors as unauthorized
        logger.warning("Session verification raised unexpectedly: %s", exc)
        raise _auth_error("jwk_failed_to_load") from exc

    if not state.is_signed_in:
        raise _auth_error(getattr(state, "reason", None))

    payload = state.payload or {}
    _validate_issuer(payload)
    return _user_from_payload(payload)