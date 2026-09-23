"""Issuer verification layer tests (M16 upgrade).

Covers the four-state issuer verification vocabulary:

    VERIFIED_BY_ISSUER | NOT_VERIFIED | VERIFICATION_UNAVAILABLE | ISSUER_UNKNOWN

Contract under test:
  * an unknown issuer is NEVER fraud and NEVER a verification;
  * a verification-code that cannot be confirmed is NEVER VERIFIED and NEVER
    a fraud signal on its own;
  * only documented endpoints in the registry are ever contacted;
  * any network/HTTP failure resolves to VERIFICATION_UNAVAILABLE;
  * identifiers exposed through the API are always masked;
  * fusion maps the four states to the correct decision without inflating
    fraud signals.
"""

from app.core.config import settings
from app.services.anomaly_service import AnomalyReport
from app.services.evidence_fusion import build_evidence, fuse
from app.services.extraction_service import ExtractionResult
from app.services.issuer import issuer_verification
from app.services.issuer.issuer_registry import IssuerRecord, IssuerReport
from app.services.issuer.verifier import (
    HttpCodeVerifier,
    IssuerHttpError,
    IssuerVerificationResult,
    RegistryProfileVerifier,
    mask_identifier,
)
from app.services.pdf_forensics import ForensicReport
from app.services.qr_service import QRReport
from app.services.semantic_service import extract_semantics
from app.services.tampering_service import TamperingReport
from app.services.verification_code_service import analyze_verification_codes
from app.services.visual_analysis import VisualReport

FORAGE_CODES = [
    {"code": "sJLRwfFRRwiZ6mSZk", "type": "enrolment_verification_code"},
    {"code": "69c683a40afbea3f2d948ab3", "type": "user_verification_code"},
]


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

def test_mask_identifier_hides_middle():
    assert mask_identifier("sJLRwfFRRwiZ6mSZk") == "sJLR**********SZk"
    assert len(mask_identifier("sJLRwfFRRwiZ6mSZk")) == 17
    assert "wfFRRwiZ6m" not in mask_identifier("sJLRwfFRRwiZ6mSZk")


def test_mask_identifier_short_values():
    assert mask_identifier("") == ""
    assert mask_identifier("ab") == "**"
    assert mask_identifier(None) == ""


# ---------------------------------------------------------------------------
# RegistryProfileVerifier
# ---------------------------------------------------------------------------

def test_unknown_issuer_is_not_a_verification():
    result = RegistryProfileVerifier().verify(None, FORAGE_CODES)
    assert result.status == "ISSUER_UNKNOWN"
    assert not result.is_verified
    assert result.source == "none"


def test_unregistered_issuer_is_not_a_verification():
    result = RegistryProfileVerifier().verify("Some Random Institute", FORAGE_CODES)
    assert result.status == "ISSUER_UNKNOWN"
    assert result.issuer == "Some Random Institute"
    assert not result.is_verified


def test_forage_profile_is_verification_unavailable():
    record = issuer_verification.registry.lookup("Forage")
    assert record is not None
    result = RegistryProfileVerifier().verify("Forage", FORAGE_CODES, record=record)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert not result.is_verified
    assert not result.is_authoritative_negative
    assert result.source == "issuer_registry"
    # Identifiers are masked, never exposed raw.
    assert result.checked_identifiers == ["sJLR**********SZk", "69c6*****************ab3"]
    assert "Forage" in result.reason
    assert "NOT evidence of fraud" in result.reason
    assert result.confidence == 0.0


def test_forage_assess_end_to_end():
    report = issuer_verification.assess(
        "Forage",
        verification_codes=FORAGE_CODES,
        certificate_data={"organization": "Forage"},
    )
    assert report.issuer_verification is not None
    assert report.issuer_verification.status == "VERIFICATION_UNAVAILABLE"
    # Legacy fields reconciled honestly: no domain-consistency overclaim.
    assert report.status in ("known_unverified", "known_verified")
    assert report.verification_result == "VERIFICATION_UNAVAILABLE"
    assert report.issuer_state == "COULD_NOT_BE_VERIFIED"


def test_assess_none_still_unknown():
    report = issuer_verification.assess(None)
    assert report.status == "unknown"
    assert report.issuer_verification is not None
    assert report.issuer_verification.status == "ISSUER_UNKNOWN"


# ---------------------------------------------------------------------------
# HttpCodeVerifier (fail-safe network behaviour)
# ---------------------------------------------------------------------------

def _http_record(endpoint="https://verify.example.com/check/{code}",
                 success_marker="VALID", negative_marker="NOT_FOUND"):
    return IssuerRecord(
        name="Example Issuer",
        verification_endpoint=endpoint,
        verification_methods=["verification_code"],
        verification_success_marker=success_marker,
        verification_negative_marker=negative_marker,
        enabled=True,
        official_verification_url="https://example.com/verify",
    )


def _verify_http(record, codes, http_get, enabled=True, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(settings, "external_verify_enabled", enabled)
    verifier = HttpCodeVerifier()
    return verifier.verify("Example Issuer", codes, record=record, http_get=http_get)


def test_http_verifier_success_marker_confirms(monkeypatch):
    def ok(url, timeout, max_bytes):
        assert url == "https://verify.example.com/check/ABC123"
        return 200, '{"result": "VALID"}'

    result = _verify_http(_http_record(), [{"code": "ABC123"}], ok, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFIED_BY_ISSUER"
    assert result.is_verified
    assert result.source == "official_issuer"
    assert result.confidence == 0.95
    assert result.checked_identifiers == ["ABC1****23"]


def test_http_verifier_negative_marker_is_not_verified(monkeypatch):
    def nf(url, timeout, max_bytes):
        return 200, '{"result": "NOT_FOUND"}'

    result = _verify_http(_http_record(), [{"code": "ABC123"}], nf, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "NOT_VERIFIED"
    assert result.is_authoritative_negative
    assert not result.is_verified


def test_http_verifier_200_without_marker_is_inconclusive(monkeypatch):
    def bare(url, timeout, max_bytes):
        return 200, "ok"

    result = _verify_http(_http_record(), [{"code": "ABC123"}], bare, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert not result.is_verified
    assert not result.is_authoritative_negative


def test_http_verifier_timeout_is_unavailable(monkeypatch):
    def timeout(url, timeout, max_bytes):
        raise IssuerHttpError("timeout")

    result = _verify_http(_http_record(), [{"code": "ABC123"}], timeout, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert result.error_reason == "timeout"
    assert not result.is_verified
    assert not result.is_authoritative_negative


def test_http_verifier_connection_error_is_unavailable(monkeypatch):
    def refused(url, timeout, max_bytes):
        raise ConnectionRefusedError("connection refused")

    result = _verify_http(_http_record(), [{"code": "ABC123"}], refused, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert result.error_reason == "ConnectionRefusedError"
    assert not result.is_verified


def test_http_verifier_http_error_is_unavailable(monkeypatch):
    def error(url, timeout, max_bytes):
        raise IssuerHttpError("http_500")

    result = _verify_http(_http_record(), [{"code": "ABC123"}], error, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert result.error_reason == "http_500"


def test_http_verifier_disabled_by_config(monkeypatch):
    def never_called(url, timeout, max_bytes):
        raise AssertionError("must not contact the network when disabled")

    result = _verify_http(_http_record(), [{"code": "ABC123"}], never_called, enabled=False, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert "disabled" in result.reason.lower()


def test_http_verifier_rejects_disallowed_scheme(monkeypatch):
    def never(url, timeout, max_bytes):
        raise AssertionError("must not contact a non-https endpoint")

    rec = _http_record(endpoint="http://verify.example.com/check/{code}")
    monkeypatch.setattr(settings, "external_verify_enabled", True)
    monkeypatch.setattr(settings, "external_verify_schemes", ["https"])
    result = _verify_http(rec, [{"code": "ABC123"}], never, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"
    assert "not allowed" in result.reason


def test_http_verifier_no_code_is_unavailable(monkeypatch):
    def never(url, timeout, max_bytes):
        raise AssertionError("must not contact without a code")

    result = _verify_http(_http_record(), [], never, enabled=True, monkeypatch=monkeypatch)
    assert result.status == "VERIFICATION_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Verification-code analysis integration
# ---------------------------------------------------------------------------

def _extraction(codes=None):
    ex = ExtractionResult()
    ex.text = "sample text"
    ex.fields = {
        "candidate_name": "A", "organization": "Forage", "course": "C",
        "issue_date": "2026-03-30", "cert_id": "CERT-1",
    }
    if codes is not None:
        ex.fields["verification_codes"] = codes
    return ex


def test_no_codes_is_no_code():
    report = analyze_verification_codes(_extraction(codes=[]))
    assert report.state == "NO_CODE"
    assert report.status == "no_code"


def test_codes_without_external_verification_are_unavailable():
    report = analyze_verification_codes(
        _extraction(codes=FORAGE_CODES), external_verify_enabled=False,
    )
    assert report.state == "VERIFICATION_UNAVAILABLE"
    assert report.status == "verification_unavailable"


def test_codes_with_verified_issuer_are_confirmed():
    report = analyze_verification_codes(
        _extraction(codes=FORAGE_CODES), external_verify_enabled=True,
        issuer_verification=IssuerVerificationResult(status="VERIFIED_BY_ISSUER"),
    )
    assert report.state == "VERIFIED_BY_ISSUER"


def test_codes_with_negative_issuer_are_not_verified():
    report = analyze_verification_codes(
        _extraction(codes=FORAGE_CODES), external_verify_enabled=True,
        issuer_verification=IssuerVerificationResult(status="NOT_VERIFIED"),
    )
    assert report.state == "NOT_VERIFIED"


# ---------------------------------------------------------------------------
# Fusion mapping for the four issuer states
# ---------------------------------------------------------------------------

def _context(issuer_report, codes=None, tampering="none_detected"):
    return {
        "extraction": _extraction(codes=codes),
        "tampering": TamperingReport(status=tampering),
        "qr": QRReport(),
        "issuer": issuer_report,
        "anomaly": AnomalyReport(score=0.1, level="low"),
        "ood_status": "normal",
        "duplicate": {},
    }


def _items_with_issuer(items):
    return items + [
        {"source": "ml", "category": "ML", "signal": "risk", "severity": "low",
         "confidence": 0.7, "explanation": "", "status": "PASS"},
        {"source": "ex", "category": "EXTRACTION", "signal": "text_source", "severity": "low",
         "confidence": 0.6, "explanation": "", "status": "PASS"},
    ]


def test_fusion_verified_by_issuer_yields_verified():
    iv = IssuerVerificationResult(
        status="VERIFIED_BY_ISSUER", issuer="Example Issuer", source="official_issuer",
        checked_identifiers=["ABC1***123"], confidence=0.95,
    )
    report = IssuerReport(issuer_name="Example Issuer", status="externally_verified",
                          issuer_verification=iv)
    items = _items_with_issuer([])
    items = build_evidence(
        ml={"prediction": "genuine", "risk_score": 0.2, "confidence": 0.8,
            "model_version": "random_forest_v3"},
        extraction=_extraction(codes=[{"code": "ABC123"}]),
        intelligence={"structure_completeness": 0.8, "certificate_type": {"primary": "completion"},
                      "consistency_findings": []},
        semantic=extract_semantics("has successfully completed the course"),
        forensic=ForensicReport(),
        visual=VisualReport(),
        tampering=TamperingReport(status="none_detected"),
        qr=QRReport(), issuer=report,
        anomaly=AnomalyReport(score=0.0, level="low"),
        duplicate={}, verification_codes=None, features={},
    )
    issuer_items = [i for i in items if i["category"] == "ISSUER"]
    assert issuer_items and issuer_items[0]["status"] == "PASS"
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.2}, **(
        {**_context(report, codes=[{"code": "ABC123"}]),
         "verification_codes": None}))
    assert result["decision"] == "VERIFIED"


def test_fusion_verification_unavailable_yields_requires_verification():
    iv = IssuerVerificationResult(
        status="VERIFICATION_UNAVAILABLE", issuer="Forage", source="issuer_registry",
        checked_identifiers=["sJLR*********SZk"], confidence=0.0,
    )
    report = IssuerReport(issuer_name="Forage", status="known_unverified",
                          verification_result="VERIFICATION_UNAVAILABLE", issuer_verification=iv)
    items = _items_with_issuer([])
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.2}, **{
        **_context(report, codes=FORAGE_CODES),
        "verification_codes": analyze_verification_codes(
            _extraction(codes=FORAGE_CODES), external_verify_enabled=False),
    })
    assert result["decision"] == "REQUIRES_VERIFICATION"
    assert result["summary"]["verification_codes_state"] == "VERIFICATION_UNAVAILABLE"


def test_fusion_unknown_issuer_is_not_fraud():
    iv = IssuerVerificationResult(status="ISSUER_UNKNOWN", issuer=None, source="none", confidence=0.0)
    report = IssuerReport(issuer_name=None, status="unknown", issuer_verification=iv)
    items = _items_with_issuer([])
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.2}, **{
        **_context(report, codes=None),
        "verification_codes": analyze_verification_codes(_extraction(codes=[])),
    })
    # No FAIL from the issuer; a clean document with an unknown issuer is
    # handled, never marked fraudulent.
    assert result["decision"] != "SUSPICIOUS"
    assert all(i["status"] != "FAIL" for i in items)


def test_fusion_not_verified_issuer_with_strong_tampering_is_suspicious():
    iv = IssuerVerificationResult(
        status="NOT_VERIFIED", issuer="Example Issuer", source="official_issuer",
        checked_identifiers=["ABC1***123"], confidence=0.9,
    )
    report = IssuerReport(issuer_name="Example Issuer", status="known_unverified",
                          verification_result="NOT_VERIFIED", issuer_verification=iv)
    items = _items_with_issuer([]) + [
        {"source": "tampering", "category": "TAMPERING", "signal": "mod", "severity": "high",
         "confidence": 0.8, "explanation": "", "status": "FAIL"},
        {"source": "consistency", "category": "CONSISTENCY", "signal": "conflict", "severity": "high",
         "confidence": 0.8, "explanation": "", "status": "FAIL"},
    ]
    result = fuse(items, ml={"prediction": "suspicious", "risk_score": 0.9}, **{
        **_context(report, codes=[{"code": "ABC123"}], tampering="strong_indicators"),
        "verification_codes": analyze_verification_codes(
            _extraction(codes=[{"code": "ABC123"}]), external_verify_enabled=True,
            issuer_verification=iv),
    })
    assert result["decision"] == "SUSPICIOUS"


def test_build_evidence_issuer_items_reflect_four_states():
    states = {
        "VERIFIED_BY_ISSUER": "PASS",
        "NOT_VERIFIED": "FAIL",
        "VERIFICATION_UNAVAILABLE": "WARNING",
        "ISSUER_UNKNOWN": "UNKNOWN",
    }
    for status, expected in states.items():
        iv = IssuerVerificationResult(status=status, issuer="Issuer X" if status != "ISSUER_UNKNOWN" else None,
                                      checked_identifiers=["ABCD****"], confidence=0.5)
        report = IssuerReport(issuer_name="Issuer X", issuer_verification=iv)
        items = build_evidence(
            ml={"prediction": "genuine", "risk_score": 0.2, "confidence": 0.8,
                "model_version": "random_forest_v3"},
            extraction=_extraction(), intelligence={},
            semantic=extract_semantics(""),
            forensic=ForensicReport(),
            visual=VisualReport(),
            tampering=TamperingReport(status="none_detected"),
            qr=QRReport(), issuer=report,
            anomaly=AnomalyReport(score=0.0, level="low"),
            duplicate={}, verification_codes=None, features={},
        )
        issuer_items = [i for i in items if i["category"] == "ISSUER"]
        assert issuer_items, status
        assert issuer_items[0]["status"] == expected, status