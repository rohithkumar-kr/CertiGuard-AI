"""Verification-code analysis.

Analyzes the credential identifiers extracted from a document (enrolment /
user verification codes, certificate IDs, reference numbers). This layer is
fully independent of the machine-learning pipeline and of the issuer registry.

Semantics enforced here (see upgrade spec):
  * a credential identifier is a POSITIVE identity signal when present, but
    extraction alone never confirms it;
  * when no issuer-side check is possible in this environment the report is
    VERIFICATION_UNAVAILABLE — never VERIFIED_BY_ISSUER and never a fraud
    signal;
  * a code that is positively confirmed against an issuer endpoint is
    VERIFIED_BY_ISSUER;
  * a code that was checked but could not be confirmed is NOT_VERIFIED
    (advisory only — a single unverifiable code is not proof of fraud).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .extraction_service import ExtractionResult
    from .issuer.verifier import IssuerVerificationResult


@dataclass
class VerificationCodeReport:
    status: str = "no_code"  # no_code | verification_unavailable | not_verified | verified_by_issuer
    state: str = "NO_CODE"   # NO_CODE | VERIFICATION_UNAVAILABLE | NOT_VERIFIED | VERIFIED_BY_ISSUER
    codes: list = field(default_factory=list)
    detail: str = ""
    notes: list = field(default_factory=list)


_CODE_SHAPE_HEX = re.compile(r"^[0-9a-fA-F]{16,64}$")
_CODE_SHAPE_ALNUM = re.compile(r"^[A-Za-z0-9]{6,64}$")


def _looks_well_formed(code: str) -> bool:
    """Advisory shape check. A well-formed code is hex-shaped or alphanumeric;
    a code with clearly implausible characters is a (mild) anomaly signal."""
    s = (code or "").strip()
    if not s:
        return False
    if _CODE_SHAPE_HEX.match(s) or _CODE_SHAPE_ALNUM.match(s):
        return True
    return bool(re.match(r"^[A-Za-z0-9._\-]{6,64}$", s))


def analyze_verification_codes(
    extraction: ExtractionResult,
    external_verify_enabled: bool = False,
    issuer_verification: IssuerVerificationResult | None = None,
) -> VerificationCodeReport:
    """Analyze credential identifiers present in an extraction result.

    ``issuer_verification`` (optional) is the authoritative result from the
    issuer verification layer. When ``external_verify_enabled`` is False, or
    when no conclusive issuer result is available, the report is
    VERIFICATION_UNAVAILABLE for any extracted code — never VERIFIED_BY_ISSUER
    and never a fraud signal.
    """
    codes = (extraction.fields or {}).get("verification_codes") or []
    report = VerificationCodeReport(codes=list(codes))

    if not codes:
        report.status = "no_code"
        report.state = "NO_CODE"
        report.detail = "No credential identifier (verification code, certificate ID or reference number) was extracted. Absence of an identifier is NOT evidence of fraud."
        report.notes.append("No verification identifier present.")
        return report

    malformed = [c for c in codes if not _looks_well_formed(c.get("code", ""))]
    if malformed:
        report.notes.append(
            f"{len(malformed)} extracted identifier(s) have an implausible shape; "
            "treated as low-integrity advisory signals, never a verdict."
        )

    if not external_verify_enabled:
        report.status = "verification_unavailable"
        report.state = "VERIFICATION_UNAVAILABLE"
        report.detail = (
            f"{len(codes)} credential identifier(s) extracted, but issuer-side "
            "verification is not available in this environment. The identifiers "
            "support the document's authenticity but could not be independently "
            "confirmed here."
        )
        report.notes.append("External issuer verification is disabled; codes are recorded but not confirmed.")
        return report

    if issuer_verification is None:
        report.status = "verification_unavailable"
        report.state = "VERIFICATION_UNAVAILABLE"
        report.detail = (
            f"{len(codes)} credential identifier(s) extracted, but no issuer-side "
            "verification result is available. The identifiers support the "
            "document's authenticity but could not be independently confirmed here."
        )
        return report

    iv_status = issuer_verification.status
    if iv_status == "VERIFIED_BY_ISSUER":
        report.status = "verified_by_issuer"
        report.state = "VERIFIED_BY_ISSUER"
        report.detail = "The credential identifier was positively confirmed against the issuer-side verification service."
    elif iv_status == "NOT_VERIFIED":
        report.status = "not_verified"
        report.state = "NOT_VERIFIED"
        report.detail = (
            f"{len(codes)} credential identifier(s) extracted, but they could "
            "not be confirmed against an issuer-side verification service. "
            "An unconfirmed code is NOT proof of fraud."
        )
    else:
        report.status = "verification_unavailable"
        report.state = "VERIFICATION_UNAVAILABLE"
        report.detail = (
            f"{len(codes)} credential identifier(s) extracted, but issuer-side "
            "verification is unavailable. The identifiers support the document's "
            "authenticity but could not be independently confirmed here."
        )
        report.notes.append(issuer_verification.reason or "Issuer verification unavailable.")
    return report


verification_code_analysis = analyze_verification_codes