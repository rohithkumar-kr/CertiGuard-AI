"""Issuer intelligence (Phase 12, M4).

Advisory issuer verification. This layer is STRICTLY independent from the
machine-learning ``issuer_known`` and ``issuer_domain_trust`` features in
``certificate_patterns.KNOWN_ISSUERS`` / ``feature_service``. It can never
change the ML feature vector.

Rules enforced here (see Phase 12 spec):
  * an unknown issuer is NOT evidence of fraud;
  * an issuer that cannot be verified externally is NOT evidence of fraud;
  * a QR/URL domain that disagrees with the issuer is *evidence* for review,
    never a fraud verdict by itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..qr_service import QRReport

_SUFFIX_WORDS = (
    "university", "academy", "institute", "college", "school", "training",
    "certification", "certifications", "education", "center", "centre",
    "council", "association", "foundation", "the", "of", "for", "and",
)
_SUFFIX_TERMS = (" ltd", " llc", " inc", " gmbh", " pvt", " corp", " plc", " sa")


@dataclass
class IssuerRecord:
    name: str
    aliases: list = field(default_factory=list)
    verification_domain: str | None = None
    verification_url_pattern: str | None = None
    issuer_type: str = "educational"
    country: str | None = None
    verification_methods: list = field(default_factory=list)
    # --- upgrade: configurable issuer verification layer ---
    # Official verification endpoint template. Only endpoints explicitly
    # documented in the registry are ever contacted. ``{code}`` is replaced by
    # the first extracted identifier. Leave empty when no public programmatic
    # verification mechanism exists.
    verification_endpoint: str | None = None
    # Identifier types this issuer mints (e.g. "enrolment_verification_code",
    # "certificate_id", "user_verification_code", "badge_uid").
    identifier_types: list = field(default_factory=list)
    # Known verification URL patterns (advisory; used for display, not fetch).
    url_patterns: list = field(default_factory=list)
    # Whether this issuer's verification profile is enabled.
    enabled: bool = True
    # Human-facing URL where a third party can verify a credential manually.
    official_verification_url: str | None = None
    # Honest explanation used when verification is unavailable for this issuer.
    verification_note: str | None = None
    # Response markers (substrings) that make an endpoint response conclusive.
    verification_success_marker: str | None = None
    verification_negative_marker: str | None = None


def derive_candidate_domains(issuer_name: str) -> list[str]:
    """Derive plausible verification domains from an issuer name.

    Heuristic only: used to decide whether a QR/URL domain is *consistent*
    with the extracted issuer. Never used to declare an issuer genuine.
    """
    name = issuer_name.strip().lower()
    if not name:
        return []
    for term in _SUFFIX_TERMS:
        name = name.replace(term, "")
    tokens = [t for t in re.split(r"[^a-z0-9]+", name) if t]
    candidates = []
    # Full slug with .com/.edu/.org
    if len(tokens) >= 2:
        slug = ".".join(tokens)
        for tld in (".com", ".edu", ".org"):
            candidates.append(slug + tld)
    # Last meaningful token (e.g. "Cisco", "AWS", "Harvard")
    meaningful = [t for t in tokens if t not in _SUFFIX_WORDS]
    if meaningful:
        head = ".".join(meaningful)
        for tld in (".com", ".edu", ".org"):
            candidates.append(head + tld)
    return candidates


@dataclass
class IssuerReport:
    issuer_name: str | None = None
    status: str = "unknown"
    registry_record: IssuerRecord | None = None
    candidate_domains: list = field(default_factory=list)
    qr_domains: list = field(default_factory=list)
    domain_consistency: str | None = None  # consistent | inconsistent | no_qr
    external: dict | None = None
    notes: list = field(default_factory=list)
    # --- richer state vocabulary (upgrade) ---
    issuer_identified: bool = False
    issuer_state: str = "ISSUER_UNKNOWN"
    # ISSUER_UNKNOWN | ISSUER_IDENTIFIED | ISSUER_VERIFIED | COULD_NOT_BE_VERIFIED
    verification_result: str = "ISSUER_UNKNOWN"
    # ISSUER_UNKNOWN | VERIFICATION_UNAVAILABLE | NOT_VERIFIED | VERIFIED_BY_ISSUER
    verification_methods: list = field(default_factory=list)
    verification_detail: str = ""
    # --- upgrade: authoritative issuer verification result ---
    # Populated by the issuer verification layer (``verifier.py``) whenever a
    # credential is assessed. Never fabricated and never guessed.
    issuer_verification: "IssuerVerificationResult | None" = None


class IssuerRegistry:
    """Registry of known issuers with verification domains.

    The registry is advisory and pluggable. It deliberately does NOT embed
    verdict rules; entries are just facts used to cross-check evidence.
    """

    def __init__(self, data_path: str | None = None) -> None:
        self.records: dict[str, IssuerRecord] = {}
        self._load(data_path or str(Path(__file__).resolve().parent / "issuer_registry.json"))

    def _load(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        for entry in data.get("issuers", []):
            rec = IssuerRecord(**entry)
            self.records[rec.name.lower()] = rec
            for alias in rec.aliases:
                self.records[alias.lower()] = rec

    def lookup(self, name: str | None) -> IssuerRecord | None:
        if not name:
            return None
        return self.records.get(name.strip().lower())


class IssuerVerificationService:
    def __init__(self, registry: IssuerRegistry | None = None,
                 adapters: list | None = None) -> None:
        from .adapters import DomainVerificationAdapter, UrlVerificationAdapter
        from .verifier import HttpCodeVerifier, IssuerVerificationResult, RegistryProfileVerifier
        self.registry = registry or IssuerRegistry()
        self.adapters = adapters or [DomainVerificationAdapter(), UrlVerificationAdapter()]
        # Issuer-side credential verification chain (authoritative).
        self._http_verifier = HttpCodeVerifier()
        self._profile_verifier = RegistryProfileVerifier()

    def verify_credential(self, issuer_name: str | None,
                          verification_codes: list | None = None,
                          certificate_data: dict | None = None) -> IssuerVerificationResult:
        """Run the issuer-side verification chain for a credential.

        Returns an ``IssuerVerificationResult``. Fail-safe by construction:
        unexpected errors resolve to VERIFICATION_UNAVAILABLE, never to a
        verification and never to a fraud signal.
        """
        record = self.registry.lookup(issuer_name)
        if self._http_verifier.can_verify(record):
            try:
                return self._http_verifier.verify(
                    issuer_name, verification_codes, certificate_data, record=record,
                )
            except Exception as exc:  # noqa: BLE001 - fail-safe, never fabricate
                return IssuerVerificationResult(
                    status="VERIFICATION_UNAVAILABLE",
                    issuer=issuer_name,
                    source="issuer_registry",
                    error_reason=type(exc).__name__,
                    reason="The issuer verification mechanism failed unexpectedly. "
                           "Network unavailability is NOT evidence of fraud.",
                    confidence=0.0,
                )
        return self._profile_verifier.verify(
            issuer_name, verification_codes, certificate_data, record=record,
        )

    def assess(self, issuer_name: str | None, qr_report: QRReport | None = None,
               external_result: dict | None = None,
               verification_codes: list | None = None,
               certificate_data: dict | None = None) -> IssuerReport:
        report = IssuerReport(issuer_name=issuer_name)
        report.issuer_verification = self.verify_credential(
            issuer_name, verification_codes, certificate_data,
        )
        if not issuer_name:
            report.status = "unknown"
            report.issuer_state = "ISSUER_UNKNOWN"
            report.verification_result = "ISSUER_UNKNOWN"
            report.domain_consistency = "no_qr"
            report.notes.append("No issuer name could be extracted.")
            return report

        report.candidate_domains = derive_candidate_domains(issuer_name)
        qr_domains = []
        if qr_report:
            qr_domains = [c.domain for c in qr_report.codes if c.domain]
        report.qr_domains = qr_domains

        record = self.registry.lookup(issuer_name)
        report.registry_record = record
        report.issuer_identified = record is not None
        report.verification_methods = list(record.verification_methods) if record else []

        # Domain consistency between QR payload and issuer.
        expected = {record.verification_domain} if record and record.verification_domain else set()
        expected |= set(report.candidate_domains)
        if qr_domains and expected:
            matches = [d for d in qr_domains
                       if any(d == e or d.endswith("." + e) or e.endswith("." + d) for e in expected)]
            report.domain_consistency = "consistent" if matches else "inconsistent"
        elif qr_domains:
            report.domain_consistency = "inconsistent"  # QR points somewhere else
        else:
            report.domain_consistency = "no_qr"

        # Run adapters.
        for adapter in self.adapters:
            try:
                result = adapter.verify(record, report, external_result)
            except Exception as exc:  # noqa: BLE001
                result = {"status": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
            if result.get("status") not in (None, "unavailable", "skipped"):
                report.external = result
                break
            if result.get("status") == "skipped":
                continue

        # Status decision (advisory).
        if report.external and report.external.get("status") == "verified":
            report.status = "externally_verified"
            report.issuer_state = "ISSUER_VERIFIED"
            report.verification_result = "VERIFIED_BY_ISSUER"
            report.verification_detail = report.external.get("detail") or "Verified against the issuer's verification service."
        elif record and record.verification_domain and report.domain_consistency == "consistent":
            report.status = "known_verified"
            report.issuer_state = "ISSUER_VERIFIED"
            report.verification_result = "VERIFIED_BY_ISSUER"
            report.verification_detail = "Issuer identity confirmed against its known verification domain."
        elif record:
            report.status = "known_unverified"
            report.issuer_state = "COULD_NOT_BE_VERIFIED"
            report.verification_result = "VERIFICATION_UNAVAILABLE"
            report.verification_detail = "Issuer identified in the registry, but no issuer-side verification could be completed in this environment."
        elif report.domain_consistency == "consistent":
            report.status = "domain_verified"
            report.issuer_state = "ISSUER_VERIFIED"
            report.verification_result = "VERIFIED_BY_ISSUER"
            report.verification_detail = "QR/URL domain is consistent with the issuer."
        elif report.domain_consistency == "inconsistent":
            report.status = "extracted_but_unverified"
            report.issuer_state = "COULD_NOT_BE_VERIFIED"
            report.verification_result = "NOT_VERIFIED"
            report.verification_detail = "QR/URL domain does not match the extracted issuer."
            report.notes.append("QR/URL domain does not match the extracted issuer.")
        else:
            report.status = "extracted_but_unverified"
            report.issuer_state = "ISSUER_UNKNOWN"
            report.verification_result = "ISSUER_UNKNOWN"
            report.verification_detail = "Issuer not present in the advisory registry."

        if report.status != "externally_verified" and report.domain_consistency != "consistent":
            report.notes.append("Issuer could not be independently verified. "
                                "This is NOT evidence of fraud.")

        # ---- Reconcile the authoritative issuer verification result ----
        # The issuer verification layer is the single source of truth for
        # whether a credential was actually verified by its issuer. Legacy
        # domain-consistency heuristics never claim a verification: a QR
        # domain that merely matches an issuer is NOT an issuer verification.
        iv = report.issuer_verification
        if iv is not None:
            if iv.status == "VERIFIED_BY_ISSUER":
                report.issuer_state = "ISSUER_VERIFIED"
                report.verification_result = "VERIFIED_BY_ISSUER"
                report.status = "externally_verified"
                report.verification_detail = iv.reason or "Verified against the issuer's verification service."
            elif iv.status == "NOT_VERIFIED":
                report.verification_result = "NOT_VERIFIED"
                report.issuer_state = "COULD_NOT_BE_VERIFIED"
                if report.status in ("externally_verified", "known_verified", "domain_verified"):
                    report.status = "known_unverified" if record else "extracted_but_unverified"
                report.verification_detail = iv.reason or "The issuer's verification service did not confirm this credential."
            elif report.verification_result == "VERIFIED_BY_ISSUER":
                # No authoritative verification is available; downgrade any
                # heuristic "domain verified" claim to an honest value.
                report.verification_result = "VERIFICATION_UNAVAILABLE"
                report.issuer_state = "COULD_NOT_BE_VERIFIED"
                if report.status in ("externally_verified", "known_verified", "domain_verified"):
                    report.status = "known_unverified" if record else "extracted_but_unverified"
                report.verification_detail = iv.reason or "Issuer could not be independently verified."
        return report


issuer_verification = IssuerVerificationService()