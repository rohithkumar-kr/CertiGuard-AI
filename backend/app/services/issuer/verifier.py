"""Issuer-side credential verification layer.

A clean, production-oriented abstraction over "can this credential be
independently verified by its issuer?". This layer is advisory: it can never
change the ML feature vector or the 31 feature definitions, and it never
emits fraud verdicts by itself.

Result status vocabulary:

    VERIFIED_BY_ISSUER        positively confirmed via an official issuer
                              verification mechanism (a real, documented,
                              reachable endpoint + matching success marker)
    NOT_VERIFIED              the issuer's authoritative check returned a
                              definitive negative (documented negative marker)
    VERIFICATION_UNAVAILABLE  no documented/observable official mechanism, or
                              the mechanism could not be reached (network /
                              timeout / 5xx / malformed response). This is
                              NOT evidence of fraud and never a verification.
    ISSUER_UNKNOWN            no issuer could be identified from the document.

Design contract:
  * only endpoints explicitly configured in the issuer registry are ever
    contacted; nothing is scraped and nothing is guessed;
  * any network/HTTP failure resolves to VERIFICATION_UNAVAILABLE, never to
    VERIFIED_BY_ISSUER and never to a fraud signal;
  * no secrets are stored or logged;
  * identifiers are masked in every result exposed through the API.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from app.core.config import settings

# Default maximum accepted response body for an endpoint check (bytes).
_DEFAULT_MAX_BYTES = 64 * 1024
_HTTP_TIMEOUT = 6.0


def mask_identifier(identifier: str) -> str:
    """Mask an identifier while preserving a recognizable prefix/suffix.

    Example: ``sJLRwfFRRwiZ6mSZk`` -> ``sJLR*********SZk``.
    """
    s = str(identifier or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "*" * len(s)
    head = s[:4]
    tail = s[-3:] if len(s) > 7 else s[-2:]
    return head + "*" * max(4, len(s) - len(head) - len(tail)) + tail


@dataclass
class IssuerVerificationResult:
    status: str = "VERIFICATION_UNAVAILABLE"
    issuer: str | None = None
    verification_method: str | None = None
    verification_url: str | None = None
    checked_identifiers: list = field(default_factory=list)
    source: str = "none"  # official_issuer | issuer_registry | none
    reason: str = ""
    confidence: float = 0.0
    timestamp: str | None = None
    error_reason: str | None = None

    @property
    def is_verified(self) -> bool:
        return self.status == "VERIFIED_BY_ISSUER"

    @property
    def is_authoritative_negative(self) -> bool:
        return self.status == "NOT_VERIFIED"

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "issuer": self.issuer,
            "verification_method": self.verification_method,
            "verification_url": self.verification_url,
            "checked_identifiers": list(self.checked_identifiers),
            "source": self.source,
            "reason": self.reason,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "error_reason": self.error_reason,
        }


class IssuerHttpError(Exception):
    """A safe, secret-free error raised when an endpoint check fails."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class IssuerVerifier:
    """Interface for issuer-side verification mechanisms."""

    provider_id = "base"

    def can_verify(self, record) -> bool:  # noqa: ANN001
        return False

    def verify(
        self,
        issuer: str | None,
        verification_codes: list | None = None,
        certificate_data: dict | None = None,
        *,
        record=None,  # noqa: ANN001
    ) -> IssuerVerificationResult:
        raise NotImplementedError


def _masked_codes(verification_codes: list | None) -> list:
    if not verification_codes:
        return []
    masked = []
    for item in verification_codes:
        if isinstance(item, dict):
            code = item.get("code") or item.get("value") or item.get("identifier")
        else:
            code = item
        masked.append(mask_identifier(str(code)) if code else "")
    return [m for m in masked if m]


class RegistryProfileVerifier(IssuerVerifier):
    """Default issuer verification based purely on the advisory registry.

    This verifier never contacts the network. It reports the best honest
    answer available offline:
      * no issuer extracted                  -> ISSUER_UNKNOWN
      * issuer not in the registry           -> ISSUER_UNKNOWN
      * issuer in registry but no documented
        programmatic verification endpoint   -> VERIFICATION_UNAVAILABLE
      * endpoint configured but external
        verification disabled by config      -> VERIFICATION_UNAVAILABLE
    """

    provider_id = "registry_profile"

    def can_verify(self, record) -> bool:  # noqa: ANN001
        return True

    def verify(
        self,
        issuer: str | None,
        verification_codes: list | None = None,
        certificate_data: dict | None = None,
        *,
        record=None,  # noqa: ANN001
    ) -> IssuerVerificationResult:
        masked = _masked_codes(verification_codes)
        if not issuer:
            return IssuerVerificationResult(
                status="ISSUER_UNKNOWN",
                issuer=None,
                source="none",
                reason="No issuer could be identified from the document.",
                confidence=0.0,
            )
        if record is None:
            return IssuerVerificationResult(
                status="ISSUER_UNKNOWN",
                issuer=issuer,
                source="none",
                reason="Issuer is not present in the advisory registry, so no issuer-side verification mechanism is configured.",
                confidence=0.0,
            )
        method = record.verification_methods[0] if record.verification_methods else "domain_check"
        official_url = record.official_verification_url or record.verification_url_pattern
        if not record.enabled:
            return IssuerVerificationResult(
                status="VERIFICATION_UNAVAILABLE",
                issuer=issuer,
                verification_method=method,
                verification_url=official_url,
                checked_identifiers=masked,
                source="issuer_registry",
                reason="Issuer verification is disabled by configuration.",
                confidence=0.0,
            )
        if not record.verification_endpoint:
            return IssuerVerificationResult(
                status="VERIFICATION_UNAVAILABLE",
                issuer=issuer,
                verification_method=method,
                verification_url=official_url,
                checked_identifiers=masked,
                source="issuer_registry",
                reason=record.verification_note
                or "Issuer-side verification is unavailable: no public programmatic verification endpoint is configured for this issuer. This is NOT evidence of fraud.",
                confidence=0.0,
            )
        return IssuerVerificationResult(
            status="VERIFICATION_UNAVAILABLE",
            issuer=issuer,
            verification_method=method,
            verification_url=official_url,
            checked_identifiers=masked,
            source="issuer_registry",
            reason="A verification endpoint is configured, but no authoritative result is available in this environment. This is NOT evidence of fraud.",
            confidence=0.0,
        )


class HttpCodeVerifier(IssuerVerifier):
    """Verifies a credential identifier against a configured HTTP endpoint.

    Only used when the issuer registry entry documents a verification
    endpoint AND external verification is enabled. Any failure (DNS, timeout,
    refused connection, non-2xx, oversized or malformed body, disallowed
    scheme) resolves to VERIFICATION_UNAVAILABLE.

    Positive/negative verdicts require an explicit, configured response
    marker (``verification_success_marker`` / ``verification_negative_marker``).
    Without a marker a 200 response is inconclusive and therefore reported as
    VERIFICATION_UNAVAILABLE — never as a verification.
    """

    provider_id = "http_endpoint"

    def can_verify(self, record) -> bool:  # noqa: ANN001
        return bool(record and record.enabled and record.verification_endpoint)

    def _build_url(self, endpoint: str, verification_codes: list) -> str | None:
        code = ""
        first = verification_codes[0] if verification_codes else None
        if isinstance(first, dict):
            code = str(first.get("code") or first.get("value") or first.get("identifier") or "")
        else:
            code = str(first or "")
        if not code:
            return None
        if "{code}" in endpoint:
            return endpoint.replace("{code}", urllib.parse.quote(code))
        return endpoint.rstrip("/") + "/" + urllib.parse.quote(code)

    @staticmethod
    def _http_get(url: str, timeout: float, max_bytes: int) -> tuple[int, str]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CertificateVerifier/1.0 (+issuer-verification)",
                "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL allowlisted below)
                body = resp.read(max_bytes + 1)
                status = int(getattr(resp, "status", None) or resp.getcode() or 0)
                if len(body) > max_bytes:
                    raise IssuerHttpError("response_too_large")
                return status, body.decode("utf-8", errors="replace")
        except IssuerHttpError:
            raise
        except (socket.timeout, TimeoutError):
            raise IssuerHttpError("timeout") from None
        except urllib.error.HTTPError as exc:
            raise IssuerHttpError(f"http_{exc.code}") from None
        except urllib.error.URLError as exc:
            raise IssuerHttpError(type(exc.reason).__name__ if exc.reason else "url_error") from None
        except (ConnectionError, OSError) as exc:
            raise IssuerHttpError(type(exc).__name__) from None
        except Exception as exc:  # noqa: BLE001
            raise IssuerHttpError(type(exc).__name__) from None

    def verify(
        self,
        issuer: str | None,
        verification_codes: list | None = None,
        certificate_data: dict | None = None,
        *,
        record=None,  # noqa: ANN001
        http_get: Callable | None = None,
        timeout: float | None = None,
        max_bytes: int | None = None,
        allowed_schemes: list | None = None,
    ) -> IssuerVerificationResult:
        masked = _masked_codes(verification_codes)
        endpoint = record.verification_endpoint if record else None
        method = record.verification_methods[0] if record and record.verification_methods else "verification_code"
        base = IssuerVerificationResult(
            issuer=issuer,
            verification_method=method,
            verification_url=endpoint,
            checked_identifiers=masked,
            source="issuer_registry",
            confidence=0.0,
        )
        if not settings.external_verify_enabled:
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "reason": "External issuer verification is disabled by configuration; the issuer endpoint was not contacted."}
            )
        if not record or not endpoint or not verification_codes:
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "reason": "No verification code is available to query the issuer endpoint."}
            )
        target = self._build_url(endpoint, verification_codes)
        if not target:
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "reason": "No usable verification identifier was extracted."}
            )
        scheme = urllib.parse.urlparse(target).scheme.lower()
        allowed = allowed_schemes or settings.external_verify_schemes or ["https"]
        if scheme not in allowed:
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "reason": f"The configured verification endpoint uses a scheme ({scheme}) that is not allowed."}
            )
        fetch = http_get or self._http_get
        try:
            status_code, body = fetch(
                target,
                timeout=timeout if timeout is not None else settings.external_verify_timeout,
                max_bytes=max_bytes or settings.external_verify_max_bytes,
            )
        except IssuerHttpError as exc:
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "error_reason": exc.kind,
                   "reason": "The issuer verification endpoint could not be reached. Network unavailability is NOT evidence of fraud."}
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe, never fabricate
            return IssuerVerificationResult(
                **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
                   "error_reason": type(exc).__name__,
                   "reason": "The issuer verification endpoint could not be reached. Network unavailability is NOT evidence of fraud."}
            )
        success_marker = (record.verification_success_marker or "").strip().lower()
        negative_marker = (record.verification_negative_marker or "").strip().lower()
        body_lower = body.lower()
        if 200 <= status_code < 300:
            if success_marker and success_marker in body_lower:
                return IssuerVerificationResult(
                    **{**base.as_dict(), "status": "VERIFIED_BY_ISSUER",
                       "source": "official_issuer",
                       "confidence": 0.95,
                       "reason": "The credential identifier was positively confirmed by the issuer's official verification service."}
                )
            if negative_marker and negative_marker in body_lower:
                return IssuerVerificationResult(
                    **{**base.as_dict(), "status": "NOT_VERIFIED",
                       "source": "official_issuer",
                       "confidence": 0.9,
                       "reason": "The issuer's verification service reported that the credential identifier could not be confirmed."}
                )
        return IssuerVerificationResult(
            **{**base.as_dict(), "status": "VERIFICATION_UNAVAILABLE",
               "reason": "The issuer endpoint responded, but without a documented success/negative marker no authoritative conclusion is possible."}
        )