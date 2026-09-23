"""Tests for PHASE 10: robust document extraction + OCR fallback.

Covers the OCR fallback pipeline (pdf_text -> OCR -> hybrid), extraction
metadata, graceful OCR failure, missing-fields-are-not-fraud semantics, the
low-extraction-confidence advisory signal, and the hard regression guards
(model artifact SHA-256, 31-feature schema, decision threshold, model version).
"""

import hashlib
import io
import pathlib

import pymupdf as fitz
import pytest

from app.core.config import settings
from app.services.extraction_service import (
    ExtractionResult,
    _core_completeness,
    _text_sufficient,
    extract_document,
)
from app.services.intelligence_service import build_intelligence, build_signals
from app.services.ocr_service import OcrResult, ocr_image, is_available
from src.features.build_features import FEATURE_COLUMNS


# --------------------------------------------------------------------------
# PDF builders
# --------------------------------------------------------------------------

def _make_image_pdf(text: str, dpi: int = 150) -> bytes:
    """Build a PDF whose visible text lives only in a raster image (no text
    layer) — simulating a scanned / image-heavy certificate."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    tmp = fitz.open()
    tpage = tmp.new_page(width=612, height=792)
    tpage.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11, fontname="helv")
    pix = tpage.get_pixmap(dpi=dpi)
    tmp.close()

    page.insert_image(fitz.Rect(0, 0, 612, 792), stream=pix.tobytes("png"))
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def _write_tmp(data: bytes, suffix: str) -> pathlib.Path:
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        fh.write(data)
        return pathlib.Path(fh.name)


CISCO_STYLE_TEXT = (
    "Cisco Networking Academy\n"
    "Introduction to modern ai\n"
    "Certificate of Completion\n"
    "ROHITH KUMAR K R IT\n"
    "Issued on: Jan 27, 2025\n"
    "Course ID: COA-2025-0117\n"
)

# Unique variant of the genuine fixture so these API tests never collide with
# the session-scoped genuine_pdf fixture used by other test modules.
META_PDF_TEXT = (
    "University of Cambridge\n"
    "Certificate of Achievement\n"
    "\n"
    "We hereby certify that Nora Lindqvist has completed the Computer Science program.\n"
    "\n"
    "Program offered by University of Cambridge\n"
    "Candidate ID: CERT-2023-554477\n"
    "Marks: 94 out of 100\n"
    "Grade: A\n"
    "Issue Date: 2023-04-18\n"
    "Signature: ____________________\n"
    "Seal: University Seal\n"
    "QR code available for verification\n"
)


# --------------------------------------------------------------------------
# Text sufficiency heuristic
# --------------------------------------------------------------------------

def test_empty_text_is_insufficient():
    assert _text_sufficient("", {}) is False


def test_short_text_is_insufficient():
    assert _text_sufficient("ROHITH KUMAR K R IT", {}) is False


def test_full_text_is_sufficient():
    from tests.conftest import GENUINE_PDF_TEXT

    fields = {"candidate_name": "John Walker"}
    assert _text_sufficient(GENUINE_PDF_TEXT, fields) is True


def test_short_text_is_insufficient_even_with_fields():
    # Below ocr_min_text_chars (40) OCR always runs — even if a field
    # happened to be detected (a <40-char text layer is not trustworthy).
    fields = {
        "candidate_name": "John Walker",
        "organization": "University of Cambridge",
        "course": "Computer Science",
        "issue_date": "2022-06-15",
        "cert_id": "CERT-2022-123455",
    }
    assert _text_sufficient("short text", fields) is False


def test_medium_text_without_core_fields_is_insufficient():
    fields = {}
    # 100 chars but no core fields -> below hybrid threshold -> OCR.
    assert _text_sufficient("some text " * 12, fields) is False


def test_long_text_without_core_fields_is_sufficient():
    fields = {}
    # >= ocr_hybrid_chars (150): the text layer is long enough to trust.
    assert _text_sufficient("some text " * 20, fields) is True


# --------------------------------------------------------------------------
# PDF text-layer path (no OCR)
# --------------------------------------------------------------------------

def test_normal_text_pdf_uses_pdf_text_method(tmp_path):
    from tests.conftest import _make_pdf, GENUINE_PDF_TEXT

    p = tmp_path / "normal.pdf"
    p.write_bytes(_make_pdf(GENUINE_PDF_TEXT))
    result = extract_document(str(p), "pdf")
    assert result.extraction_method == "pdf_text"
    assert result.ocr_used is False
    assert result.ocr_failed is False
    assert result.ocr_pages == 0
    assert result.extraction_confidence is not None
    assert result.extraction_confidence >= 0.6
    assert result.extraction_completeness >= 0.8
    assert result.fields["candidate_name"] == "John Walker"
    assert result.fields["organization"] == "University of Cambridge"


def test_pdf_text_confidence_scales_with_completeness():
    full = {
        "candidate_name": "John Walker",
        "organization": "University of Cambridge",
        "course": "Computer Science",
        "issue_date": "2022-06-15",
        "cert_id": "CERT-2022-123455",
    }
    assert _pdf_text_confidence(full) == 0.95

    partial = {"candidate_name": "John Walker"}
    assert _pdf_text_confidence(partial) == pytest.approx(0.68, abs=0.01)


def _pdf_text_confidence(fields: dict) -> float:
    comp = _core_completeness(fields)
    return round(min(0.6 + 0.4 * comp, 0.95), 4)


# --------------------------------------------------------------------------
# OCR fallback paths
# --------------------------------------------------------------------------

@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_image_only_pdf_recovers_fields_via_ocr(tmp_path):
    p = tmp_path / "image_only.pdf"
    p.write_bytes(_make_image_pdf(CISCO_STYLE_TEXT))
    result = extract_document(str(p), "pdf")

    assert result.ocr_used is True
    assert result.ocr_failed is False
    assert result.ocr_pages == 1
    assert result.extraction_method in ("ocr", "hybrid")
    assert result.extraction_confidence is not None
    assert result.extraction_confidence > 0.4

    # Core identity fields recovered from the OCR'd text.
    assert result.fields["candidate_name"] == "ROHITH KUMAR K R IT"
    assert result.fields["organization"] == "Cisco Networking Academy"
    assert result.fields["course"] == "Introduction to modern ai"
    assert result.fields["issue_date"] == "2025-01-27"
    assert result.extraction_completeness >= 0.8


@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_tiny_text_layer_triggers_hybrid_ocr(tmp_path):
    """A PDF with a small accessibility text layer but a rasterized body must
    be treated as image-heavy and run OCR (the real-world Cisco case)."""
    tiny_layer = "ROHITH KUMAR K R IT"
    p = tmp_path / "tiny_layer.pdf"
    p.write_bytes(_make_image_pdf(CISCO_STYLE_TEXT))
    # Inject a tiny text layer on top of the image.
    doc = fitz.open(str(p))
    page = doc[0]
    page.insert_text((72, 40), tiny_layer, fontsize=8, fontname="helv")
    data = doc.tobytes()
    doc.close()
    p.write_bytes(data)

    result = extract_document(str(p), "pdf")
    assert result.ocr_used is True
    assert result.extraction_method == "hybrid"
    assert result.extraction_confidence is not None
    # The OCR layer restored the full identity.
    assert result.fields["organization"] == "Cisco Networking Academy"
    assert result.fields["candidate_name"] == "ROHITH KUMAR K R IT"
    assert result.extraction_completeness >= 0.8


@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_ocr_image_on_numpy_input_returns_text():
    from PIL import Image

    img = Image.new("RGB", (800, 400), "white")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.text((40, 120), "Cisco Networking Academy 2025", fill="black")
    result = ocr_image(img)
    assert result.failed is False
    assert "Cisco" in result.text


# --------------------------------------------------------------------------
# Graceful OCR failure
# --------------------------------------------------------------------------

def test_ocr_failure_does_not_crash(monkeypatch, tmp_path):
    from tests.conftest import _make_pdf

    p = tmp_path / "image_only.pdf"
    p.write_bytes(_make_image_pdf(CISCO_STYLE_TEXT))

    def _failing_ocr(image):
        return OcrResult(failed=True, engine="rapidocr", error="engine boom")

    monkeypatch.setattr("app.services.extraction_service.ocr_image", _failing_ocr)
    result = extract_document(str(p), "pdf")

    assert result.ocr_failed is True
    assert result.ocr_used is False
    assert result.extraction_method in ("pdf_text", "none")
    assert any("manual review" in w for w in result.warnings)

    # Missing fields stay missing; no fraud is asserted from OCR failure.
    assert result.fields.get("candidate_name") in (None, "")
    assert result.fields.get("organization") in (None, "")


def test_ocr_failure_produces_low_confidence_signal(monkeypatch, tmp_path):
    p = tmp_path / "image_only.pdf"
    p.write_bytes(_make_image_pdf(CISCO_STYLE_TEXT))

    def _failing_ocr(image):
        return OcrResult(failed=True, engine="rapidocr", error="engine boom")

    monkeypatch.setattr("app.services.extraction_service.ocr_image", _failing_ocr)
    result = extract_document(str(p), "pdf")

    intelligence = build_intelligence(result, result.visual)
    signals = build_signals(intelligence, result, {})
    keys = [s["key"] for s in signals["risk"]]
    assert "low_extraction_confidence" in keys
    low = next(s for s in signals["risk"] if s["key"] == "low_extraction_confidence")
    assert "manual review" in low.get("detail", "")


def test_image_without_ocr_marks_failed_and_missing(tmp_path):
    from PIL import Image

    p = tmp_path / "scan.png"
    Image.new("RGB", (600, 400), "white").save(p)
    result = extract_document(str(p), "png")
    assert result.ocr_failed is True
    assert result.extraction_method == "none"
    assert result.extraction_confidence == 0.0
    assert result.fields.get("candidate_name") is None


# --------------------------------------------------------------------------
# Extraction metadata + API persistence
# --------------------------------------------------------------------------

def test_extraction_metadata_in_api_response(client):
    from tests.conftest import _make_pdf

    resp = client.post(
        "/api/verify",
        files={"file": ("meta.pdf", _make_pdf(META_PDF_TEXT), "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    extraction = body.get("extraction")
    assert extraction is not None
    assert extraction["method"] == "pdf_text"
    assert extraction["confidence_level"] in ("high", "medium", "low")
    assert extraction["fields_detected"] >= 4
    assert extraction["fields_total"] == 5
    assert extraction["ocr_used"] is False
    assert extraction["ocr_failed"] is False
    assert "confidence" in extraction
    assert "text_length" in extraction
    assert "completeness" in extraction


def test_extraction_metadata_persisted_in_db(client, db_session):
    from tests.conftest import _make_pdf
    from app.models.verification import Verification

    resp = client.post(
        "/api/verify",
        files={"file": ("persist.pdf", _make_pdf(META_PDF_TEXT), "application/pdf")},
    )
    assert resp.status_code == 200
    vid = resp.json()["verification_id"]
    record = (
        db_session.query(Verification)
        .filter(Verification.verification_id == vid)
        .first()
    )
    assert record is not None
    assert record.extraction_metadata is not None
    import json

    meta = json.loads(record.extraction_metadata)
    assert meta["method"] == "pdf_text"
    assert meta["fields_total"] == 5

    detail = client.get(f"/api/verifications/{vid}")
    assert detail.status_code == 200
    assert detail.json().get("extraction", {}).get("method") == "pdf_text"


# --------------------------------------------------------------------------
# Hard regression guards (Phase 9/10 invariants)
# --------------------------------------------------------------------------

PROD_ARTIFACT_SHA256 = "e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337"


def test_model_artifact_hash_unchanged():
    artifact = settings.model_artifact_dir / "random_forest_v3" / "model.joblib"
    assert artifact.exists()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert digest == PROD_ARTIFACT_SHA256


def test_feature_schema_still_31_features():
    assert len(FEATURE_COLUMNS) == 31


def test_decision_threshold_still_0_5():
    assert settings.decision_threshold == 0.5


def test_model_version_still_v3():
    assert settings.model_version == "random_forest_v3"


# --------------------------------------------------------------------------
# Phase 10.5 regression: generic course-title extraction (Cisco CCNA false
# positive). The CCNA certificate embeds a full text layer ("CCNA:
# Introduction to Networks") that no fixed COURSE_KEYWORDS entry covers, so
# course_present was 0 and risk sat just above the 0.5 threshold. The fix is
# a generic, layout-independent phrase/label extractor that runs on ALL text
# (PDF layer and OCR alike) — never a certificate-specific bypass.
# --------------------------------------------------------------------------

CCNA_TEXT = (
    "This certificate is awarded to\n"
    "ROHITH KUMAR K R IT\n"
    "for successfully completing\n"
    "CCNA: Introduction to Networks\n"
    "offered by Chennai Institute of Technology\n"
    "through the Cisco Networking Academy program.\n"
    "Senthil Kumar Sidharthan\n"
    "Instructor\n"
    "Chennai Institute of Technology\n"
    "18 Nov 2025\n"
    "Completion Date\n"
)


def test_generic_course_phrase_extracts_ccna():
    from app.services.extraction_service import _extract_course_phrase

    assert _extract_course_phrase(CCNA_TEXT) == "CCNA: Introduction to Networks"


def test_generic_course_label_extracts_labeled_course():
    from app.services.extraction_service import _extract_course_phrase

    labeled = "Acme Training Ltd\nCourse: Advanced Network Security\nAwarded to Sara Chen\non 2024-05-01.\n"
    assert _extract_course_phrase(labeled) == "Advanced Network Security"


def test_course_phrase_does_not_match_lowercase_connectors():
    """The completion-phrase regex must not skip a lowercase connector
    ("the", "all", ...) to grab a later title — that would fabricate a course
    from unrelated prose."""
    from app.services.extraction_service import _extract_course_phrase

    assert _extract_course_phrase(
        "This certificate acknowledges completion of the Physics program."
    ) is None
    assert _extract_course_phrase(
        "We are pleased to present this certificate to Maya Patel\n"
        "for completing all assignments and assessments in Web Development."
    ) is None


def test_ccna_certificate_extracts_course_and_predicts_genuine(client):
    from tests.conftest import _make_pdf

    resp = client.post(
        "/api/verify",
        files={
            "file": (
                "ccna_intro_to_networks.pdf",
                _make_pdf(CCNA_TEXT),
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    # The generic extractor recovered the course from the embedded text layer.
    assert body["extraction"]["method"] == "pdf_text"
    assert body["extraction"]["ocr_used"] is False
    assert body["extracted"]["course"] == "CCNA: Introduction to Networks"
    assert body["extracted"]["organization"] == "Chennai Institute of Technology"
    assert body["extracted"]["issue_date"] == "2025-11-18"

    # The course now sits below the decision threshold as a legitimate cert.
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5


@pytest.mark.skipif(not is_available(), reason="No OCR engine available")
def test_phase10_cisco_certificate_still_genuine_after_generic_course_fix(
    client,
):
    """The image-only Phase 10 Cisco certificate must remain genuine — the
    generic phrase extractor must not disturb the OCR recovery path."""
    from tests.conftest import _make_pdf

    resp = client.post(
        "/api/verify",
        files={
            "file": (
                "cisco_intro_to_modern_ai.png.pdf",
                _make_image_pdf(CISCO_STYLE_TEXT),
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extracted"]["course"] == "Introduction to modern ai"
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5


def test_fraud_with_detectable_course_stays_suspicious(client):
    """A fraud document that now yields a course via the generic extractor
    (future date) must STILL be flagged suspicious — generic course recovery
    must never weaken fraud detection."""
    from tests.conftest import _make_pdf

    fraud_text = (
        "Online Degree Emporium\n"
        "Certificate of Completion\n"
        "for successfully completing\n"
        "CCNA: Introduction to Networks\n"
        "offered by Online Degree Emporium\n"
        "26 Dec 2030\n"
        "Completion Date\n"
    )
    resp = client.post(
        "/api/verify",
        files={
            "file": (
                "fraud_with_course.pdf",
                _make_pdf(fraud_text),
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extracted"]["course"] == "CCNA: Introduction to Networks"
    assert body["prediction"] == "suspicious"
    assert body["risk_score"] > 0.5