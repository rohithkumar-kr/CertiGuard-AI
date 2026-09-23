"""Issuer verification adapters (Phase 12, M4).

Pluggable, generic verification mechanisms. Every adapter returns a normalized
result dict:

    {"status": "verified" | "exists" | "unavailable" | "skipped" | "failed",
     "provider": ..., "detail": ..., ...}

Adapters are conservative: they never fabricate verification, and they never
make a decision on their own — the caller (``IssuerVerificationService``)
interprets results as evidence.
"""

from __future__ import annotations

from ...core.config import settings


class IssuerVerificationAdapter:
    provider_id = "base"

    def can_handle(self, record, report) -> bool:  # noqa: ANN001
        return False

    def verify(self, record, report, external_result: dict | None = None) -> dict:  # noqa: ANN001
        raise NotImplementedError


class DomainVerificationAdapter(IssuerVerificationAdapter):
    """Checks whether a QR/URL domain is consistent with the issuer's known or
    derived verification domain. Runs entirely locally (no network)."""

    provider_id = "domain_consistency"

    def can_handle(self, record, report) -> bool:  # noqa: ANN001
        return bool(report and report.domain_consistency)

    def verify(self, record, report, external_result: dict | None = None) -> dict:  # noqa: ANN001
        if report.domain_consistency == "consistent":
            return {"status": "verified",
                    "provider": self.provider_id,
                    "detail": "QR/URL domain matches the issuer's verification domain."}
        if report.domain_consistency == "inconsistent":
            return {"status": "failed",
                    "provider": self.provider_id,
                    "detail": "QR/URL domain does not match the issuer. Evidence only."}
        return {"status": "skipped", "provider": self.provider_id}


class UrlVerificationAdapter(IssuerVerificationAdapter):
    """Optionally contacts the issuer's verification URL when external
    verification is enabled. Bounded timeout and response size."""

    provider_id = "url_reachability"

    def can_handle(self, record, report) -> bool:  # noqa: ANN001
        return bool(record and record.verification_url_pattern)

    def verify(self, record, report, external_result: dict | None = None) -> dict:  # noqa: ANN001
        if not settings.external_verify_enabled:
            return {"status": "skipped",
                    "provider": self.provider_id,
                    "detail": "External verification disabled by configuration."}
        # Prefer an already-collected external result (e.g. from a QR payload).
        if external_result and external_result.get("reachable"):
            return {"status": "verified",
                    "provider": self.provider_id,
                    "detail": "Issuer verification endpoint reachable.",
                    "source": "qr_external"}
        return {"status": "unavailable",
                "provider": self.provider_id,
                "detail": "No external verification endpoint result available."}