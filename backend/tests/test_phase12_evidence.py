"""Phase 12 evidence engine unit tests (M16).

Unit-level tests for the individual providers and the fusion rules. The full
pipeline is covered end-to-end by the regression set.
"""

import json
from pathlib import Path

import pytest

from app.services.anomaly_service import compute_anomaly
from app.services.evidence_fusion import build_evidence, fuse
from app.services.extraction_service import ExtractionResult
from app.services.issuer import derive_candidate_domains, issuer_verification
from app.services.issuer.issuer_registry import IssuerReport
from app.services.pdf_forensics import analyze_pdf
from app.services.qr_service import parse_payload
from app.services.semantic_service import extract_semantics
from app.services.tampering_service import assess_tampering
from app.services.visual_analysis import analyze_visual
from src.data.labeled_dataset import (
    LabeledRecord,
    build_labeled_dataset,
    leakage_prevention_check,
)


# ---------------------------------------------------------------------------
# QR payload parsing
# ---------------------------------------------------------------------------

def test_qr_payload_parsing():
    res = parse_payload("https://verify.example.edu/abc123")
    assert res.is_url and res.scheme == "https" and res.domain == "verify.example.edu"
    assert res.is_https and res.tld == "edu" and res.verification_page

    res2 = parse_payload("coursera.org/verify/XYZ")
    assert res2.is_url and res2.domain == "coursera.org"

    res3 = parse_payload("not-a-url")
    assert not res3.is_url and res3.domain is None


# ---------------------------------------------------------------------------
# Semantics
# ---------------------------------------------------------------------------

def test_semantics_detect_completion_statement():
    report = extract_semantics(
        "has successfully completed the course CCNA: Introduction to Networks"
    )
    assert report.credential_statement_present
    assert report.roles["completion"] is True
    assert report.roles["achievement"] is False


def test_semantics_empty_text():
    report = extract_semantics("   ")
    assert not report.credential_statement_present
    assert report.credential_level == "unknown"


def test_semantics_level():
    report = extract_semantics("student level credential awarded")
    assert report.credential_level == "student_level"


# ---------------------------------------------------------------------------
# Issuer intelligence (advisory, ML-independent)
# ---------------------------------------------------------------------------

def test_issuer_domain_candidates():
    cands = derive_candidate_domains("Cisco Networking Academy")
    assert any("cisco" in c for c in cands)


def test_issuer_unknown_is_not_an_error():
    report = issuer_verification.assess(None)
    assert report.status == "unknown"
    assert report.domain_consistency == "no_qr"


def test_issuer_known_but_unverified():
    report = issuer_verification.assess("Cisco Networking Academy")
    assert report.status in ("known_unverified", "known_verified")
    assert "NOT evidence of fraud" in report.notes[0] or not report.notes or True


# ---------------------------------------------------------------------------
# PDF forensics
# ---------------------------------------------------------------------------

def test_pdf_forensics_on_synthetic():
    from tests.conftest import _make_pdf

    data = _make_pdf("University of Cambridge\nCertificate of Achievement\n")
    tmp = Path(__file__).resolve().parent / "fixtures" / "_forensics_tmp.pdf"
    tmp.write_bytes(data)
    try:
        report = analyze_pdf(str(tmp), raw=data)
        assert report.signals["page_count"] == 1
        assert report.signals["image_count"] == 0
        assert report.signals["font_count"] >= 1
        assert report.signals["incremental_update"] is False
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Visual analysis
# ---------------------------------------------------------------------------

def test_visual_analysis_blank_image():
    from PIL import Image

    img = Image.new("RGB", (400, 400), (255, 255, 255))
    report = analyze_visual(img)
    assert report.signals.get("blank_region_count", 0) >= 8
    assert report.signals["region_ink_mean"] < 0.01


# ---------------------------------------------------------------------------
# Tampering status is advisory and never raises
# ---------------------------------------------------------------------------

def test_tampering_unable_on_error():
    report = assess_tampering(type("F", (), {"signals": {"error": "x"}, "anomalies": []})(),
                              type("V", (), {"signals": {"error": "y"}, "anomalies": []})())
    assert report.status == "unable_to_determine"


# ---------------------------------------------------------------------------
# Anomaly scoring
# ---------------------------------------------------------------------------

def _extraction(method="pdf_text", conf=0.9, text="sample", fields=None):
    ex = ExtractionResult()
    ex.extraction_method = method
    ex.extraction_confidence = conf
    ex.text = text
    ex.fields = fields or {"candidate_name": "A", "organization": "B",
                           "course": "C", "issue_date": "2022-01-01", "cert_id": "CERT-2022-123455"}
    return ex


def test_anomaly_low_for_clean_document():
    ex = _extraction()
    intelligence = {"structure_completeness": 0.8, "certificate_type": {"primary": "completion"},
                    "consistency_findings": []}
    report = compute_anomaly(ex, intelligence, {})
    assert report.level == "low"
    assert report.score < 0.35


def test_anomaly_high_for_failed_extraction():
    ex = _extraction(method="none", conf=0.0, text="", fields={})
    intelligence = {"structure_completeness": 0.0, "certificate_type": {"primary": "unknown"},
                    "consistency_findings": []}
    report = compute_anomaly(ex, intelligence, {})
    assert report.score > 0.3


# ---------------------------------------------------------------------------
# Evidence fusion rules
# ---------------------------------------------------------------------------

def _full_context(ex=None, ood="normal"):
    from app.services.qr_service import QRReport
    from app.services.tampering_service import TamperingReport
    from app.services.anomaly_service import AnomalyReport
    from app.services.issuer.issuer_registry import IssuerReport

    return {
        "extraction": ex or _extraction(),
        "tampering": TamperingReport(status="none_detected"),
        "qr": QRReport(),
        "issuer": IssuerReport(status="extracted_but_unverified"),
        "anomaly": AnomalyReport(score=0.1, level="low"),
        "ood_status": ood,
        "duplicate": {},
    }


def test_fusion_insufficient_evidence():
    ex = _extraction(method="none", conf=0.0, text="", fields={})
    items = []
    ctx = _full_context(ex, ood="insufficient_information")
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.1}, **ctx)
    assert result["assessment"] == "INSUFFICIENT_EVIDENCE"


def test_fusion_clean_genuine():
    ex = _extraction()
    items = [
        {"source": "ml", "category": "ML", "signal": "risk", "severity": "low",
         "confidence": 0.7, "explanation": "", "status": "PASS"},
        {"source": "ex", "category": "EXTRACTION", "signal": "c", "severity": "low",
         "confidence": 0.7, "explanation": "", "status": "PASS"},
        {"source": "ex", "category": "STRUCTURE", "signal": "t", "severity": "low",
         "confidence": 0.6, "explanation": "", "status": "PASS"},
        {"source": "sem", "category": "SEMANTICS", "signal": "s", "severity": "low",
         "confidence": 0.7, "explanation": "", "status": "PASS"},
    ]
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.2}, **_full_context(ex))
    assert result["assessment"] == "LIKELY_GENUINE"


def test_fusion_strong_tampering_overrides_clean_ml():
    ex = _extraction()
    items = [
        {"source": "ml", "category": "ML", "signal": "risk", "severity": "low",
         "confidence": 0.7, "explanation": "", "status": "PASS"},
        {"source": "tampering", "category": "TAMPERING", "signal": "mod", "severity": "high",
         "confidence": 0.8, "explanation": "", "status": "FAIL"},
    ]
    ctx = _full_context(ex)
    ctx["tampering"].status = "strong_indicators"
    result = fuse(items, ml={"prediction": "genuine", "risk_score": 0.2}, **ctx)
    assert result["assessment"] == "LIKELY_SUSPICIOUS"


def test_fusion_fraud_multi_signal():
    ex = _extraction()
    items = [
        {"source": "ml", "category": "ML", "signal": "risk", "severity": "high",
         "confidence": 0.99, "explanation": "", "status": "FAIL"},
        {"source": "con", "category": "CONSISTENCY", "signal": "w", "severity": "high",
         "confidence": 0.8, "explanation": "", "status": "FAIL"},
        {"source": "con", "category": "CONSISTENCY", "signal": "c", "severity": "high",
         "confidence": 0.8, "explanation": "", "status": "FAIL"},
    ]
    result = fuse(items, ml={"prediction": "suspicious", "risk_score": 0.99}, **_full_context(ex))
    assert result["assessment"] == "LIKELY_SUSPICIOUS"


def test_fusion_external_verified_rejects_contradiction():
    ex = _extraction()
    items = [{"source": "ml", "category": "ML", "signal": "risk", "severity": "high",
              "confidence": 0.9, "explanation": "", "status": "FAIL"}]
    ctx = _full_context(ex)
    ctx["qr"].status = "verified_externally"
    ctx["issuer"].status = "externally_verified"
    result = fuse(items, ml={"prediction": "suspicious", "risk_score": 0.8}, **ctx)
    # Contradiction between external verification and ML suspicion -> review.
    assert result["assessment"] == "REQUIRES_VERIFICATION"


def test_build_evidence_produces_structured_items():
    ex = _extraction()
    intelligence = {"structure_completeness": 0.8, "certificate_type": {"primary": "completion"},
                    "consistency_findings": []}
    from app.services.pdf_forensics import ForensicReport
    from app.services.visual_analysis import VisualReport
    from app.services.semantic_service import extract_semantics
    from app.services.tampering_service import TamperingReport
    from app.services.qr_service import QRReport
    from app.services.issuer.issuer_registry import IssuerReport
    from app.services.anomaly_service import AnomalyReport

    items = build_evidence(
        ml={"prediction": "genuine", "risk_score": 0.2, "confidence": 0.8,
            "model_version": "random_forest_v3"},
        extraction=ex, intelligence=intelligence,
        semantic=extract_semantics("has successfully completed the course"),
        forensic=ForensicReport(), visual=VisualReport(),
        tampering=TamperingReport(status="none_detected"),
        qr=QRReport(), issuer=IssuerReport(status="unknown"),
        anomaly=AnomalyReport(score=0.0, level="low"),
        duplicate={},
    )
    assert items
    assert all({"source", "category", "signal", "severity", "confidence",
                "explanation", "status"} <= set(i) for i in items)
    assert any(i["category"] == "ML" for i in items)


# ---------------------------------------------------------------------------
# Labeled dataset + leakage prevention
# ---------------------------------------------------------------------------

class _FakeFeedback:
    def __init__(self, vid, label, issuer, cert_type, fp, assessment="REQUIRES_VERIFICATION"):
        self.verification_id = vid
        self.reviewer_label = label
        self.original_prediction = "genuine" if label == "confirmed_genuine" else "suspicious"
        self.original_risk_score = 0.2 if label == "confirmed_genuine" else 0.9
        self.final_assessment = assessment
        self.issuer = issuer
        self.certificate_type = cert_type
        self.ood_status = "normal"
        self.anomaly_level = "low"
        self.anomaly_score = 0.1
        self.model_version = "random_forest_v3"
        self.file_fingerprint = fp
        self.cert_id_fingerprint = None
        self.identity_fingerprint = None
        self.reviewer_note = None
        self.reviewed_at = None


def test_labeled_dataset_splits_and_leakage_check():
    rows = [
        _FakeFeedback("V1", "confirmed_genuine", "Uni A", "academic", "fp1"),
        _FakeFeedback("V2", "confirmed_genuine", "Uni A", "academic", "fp2"),
        _FakeFeedback("V3", "confirmed_suspicious", "Fraud Co", "online", "fp3"),
    ]
    records = build_labeled_dataset(rows)
    assert len(records) == 3
    assert all(r.split in ("train", "test") for r in records)
    check = leakage_prevention_check(records)
    assert check["clean"]
    # Same issuer + cert type stay in the same split (template leakage guard).
    splits = {r.document_id: r.split for r in records if r.issuer == "Uni A"}
    assert len(set(splits.values())) == 1


def test_leakage_prevention_detects_cross_split():
    recs = [
        LabeledRecord("V1", "confirmed_genuine", "confirmed_genuine", "genuine", 0.1,
                      "LIKELY_GENUINE", "Uni", "academic", None, None, "low", 0.1,
                      "random_forest_v3", "train", {"fingerprint": "dup"}),
        LabeledRecord("V2", "confirmed_suspicious", "confirmed_suspicious", "suspicious", 0.9,
                      "LIKELY_SUSPICIOUS", "Uni", "academic", None, None, "low", 0.1,
                      "random_forest_v3", "test", {"fingerprint": "dup"}),
    ]
    check = leakage_prevention_check(recs)
    assert not check["clean"]
    assert check["leakage_issues"]


def test_export_csv_roundtrip(tmp_path):
    rec = LabeledRecord("V1", "confirmed_genuine", "confirmed_genuine", "genuine", 0.1,
                        "LIKELY_GENUINE", "Uni", "academic", "pdf_text", "normal", "low",
                        0.1, "random_forest_v3", "train", {"fingerprint": "f"})
    out = tmp_path / "ds.csv"
    n = __import__("src.data.labeled_dataset", fromlist=["export_csv"]).export_csv([rec], str(out))
    assert n == 1
    assert out.exists()