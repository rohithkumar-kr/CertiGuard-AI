"""Certificate intelligence layer (Phase 8).

Produces a structured, human-readable picture of a verified document:

  - certificate type (academic / completion / training / online / technical /
    workshop) with a single primary label
  - extracted identity (recipient, issuer, course, date, certificate ID,
    marks/grade) with safe missing-field representation
  - structural signals (signature, seal, QR, URL, issuer trust, ID validity,
    date consistency, grade/marks consistency)
  - document quality indicators (blank/empty, text extraction quality, visual
    quality, noise, sharpness)
  - positive trust signals vs risk signals (explanation engine, 8B)
  - three-level review status (low_risk / manual_review / high_risk, 8C)

This layer is advisory: it NEVER modifies the production ML prediction,
threshold, or feature schema. Missing fields are reported as missing, not as
fraud.
"""

from src.data import certificate_patterns as cp

from app.services.consistency_service import build_consistency_findings
from app.services.extraction_service import ExtractionResult

# ---------------------------------------------------------------------------
# Review-status thresholds (documented, tested, and versioned).
# ---------------------------------------------------------------------------
# These are advisory heuristics layered on top of the validated ML decision
# threshold (0.5). They do not change the production prediction boundary.
REVIEW_BAND_MIN = 0.30   # genuine with risk_score >= this -> manual_review
HIGH_RISK_THRESHOLD = 0.50  # model decision threshold; >= this -> high_risk
MIN_MEDIUM_SIGNALS_FOR_REVIEW = 2  # >= this many medium risk signals -> review
HIGH_SIGNAL_FORCES_REVIEW = True   # any high-severity risk signal -> review


def derive_certificate_types(features: dict, text: str, issuer: str) -> dict:
    """Certificate-type flags from features (ML-trained types) plus the
    intelligence-only flags (online, workshop)."""
    flags = {
        "academic": int(features.get("certificate_type_academic", 0)),
        "completion": int(features.get("certificate_type_completion", 0)),
        "training": int(features.get("certificate_type_training", 0)),
        "technical": int(features.get("certificate_type_technical", 0)),
    }
    detected = cp.certificate_type_flags(text, issuer)
    flags["online"] = int(any(k in (text or "").lower() for k in ("online", "e-learning", "elearning")))
    flags["workshop"] = int(detected.get("workshop", 0))
    return flags


_TYPE_ORDER = ["academic", "technical", "training", "completion", "online", "workshop"]


def primary_certificate_type(flags: dict) -> str:
    for name in _TYPE_ORDER:
        if flags.get(name):
            return name
    return "unknown"


def _signature_seal_qr(fields: dict) -> dict:
    return {
        "signature": {"label": "Signature", "present": bool(fields.get("has_signature"))},
        "seal": {"label": "Seal / Stamp", "present": bool(fields.get("has_seal"))},
        "qr": {"label": "QR / Barcode", "present": bool(fields.get("has_qr"))},
        "url": {"label": "External URL", "present": bool(fields.get("has_url"))},
    }


def _quality_indicators(extraction: ExtractionResult) -> dict:
    visual = extraction.visual or {}
    blank = float(visual.get("visual_blank_ratio", 0.0))
    sharpness = float(visual.get("visual_sharpness", 0.0))
    noise = float(visual.get("visual_noise", 0.0))
    color_anomaly = bool(visual.get("visual_color_anomaly"))

    text = (extraction.text or "").strip()
    blank_doc = not text and blank < 0.02
    text_ok = len(text) > 0
    visual_ok = blank < 0.5 and not color_anomaly
    quality_ok = visual_ok and text_ok

    # Phase 10: report how the text was obtained (or why it was not).
    if text_ok:
        text_extraction_quality = "ok"
    elif extraction.ocr_failed:
        text_extraction_quality = "failed"
    else:
        text_extraction_quality = "missing"

    return {
        "blank_document": blank_doc,
        "text_extraction_quality": text_extraction_quality,
        "text_present": text_ok,
        "visual_quality": "ok" if visual_ok else "attention",
        "noise": round(noise, 4),
        "sharpness": round(sharpness, 4),
        "blank_ratio": blank,
        "color_anomaly": color_anomaly,
        "extraction_method": extraction.extraction_method or "none",
        "extraction_confidence": extraction.extraction_confidence,
        "ocr_used": bool(extraction.ocr_used),
        "ocr_failed": bool(extraction.ocr_failed),
        "processing_warnings": list(extraction.warnings or []),
    }


def build_intelligence(extraction: ExtractionResult, features: dict) -> dict:
    """Assemble the full certificate intelligence record (8A)."""
    fields = extraction.fields or {}
    text = extraction.text or ""
    issuer = fields.get("organization") or ""

    flags = derive_certificate_types(features, text, issuer)
    primary = primary_certificate_type(flags)
    consistency = build_consistency_findings(extraction)

    structural = _signature_seal_qr(fields)
    quality = _quality_indicators(extraction)

    return {
        "certificate_type": {
            "flags": flags,
            "primary": primary,
        },
        "identity": consistency["identity"],
        "structural_signals": structural,
        "quality_indicators": quality,
        "consistency_findings": consistency["findings"],
        "consistency_checks": consistency["checks"],
        "structure_completeness": consistency["structure_completeness"],
        "issuer_status": consistency["issuer_status"],
        "certificate_id_status": consistency["certificate_id_status"],
        "date_status": consistency["date_status"],
        "recipient_status": consistency["recipient_status"],
        "course_status": consistency["course_status"],
    }


# ---------------------------------------------------------------------------
# Explanation engine (8B)
# ---------------------------------------------------------------------------

def _add(signals: list, key: str, label: str, status: str, detail: str,
         severity: str = "low") -> None:
    signals.append({
        "key": key, "label": label, "status": status,
        "severity": severity, "detail": detail,
    })


def build_signals(intelligence: dict, extraction: ExtractionResult,
                  features: dict) -> dict:
    """Build positive trust signals and risk signals (8B).

    Positive signals use status 'ok'; risk signals use status 'attention'.
    Wording never claims a feature "proves fraud" — signals are detected
    indicators that require assessment.
    """
    fields = extraction.fields or {}
    text = extraction.text or ""
    consistency = intelligence["consistency_findings"]
    identity = intelligence["identity"]
    flags = intelligence["certificate_type"]["flags"]
    quality = intelligence["quality_indicators"]

    positive: list[dict] = []
    risk: list[dict] = []
    ok = "ok"
    attn = "attention"

    def add_ok(key, label, detail):
        _add(positive, key, label, ok, detail, severity="low")

    def add_risk(key, label, detail, severity="medium"):
        _add(risk, key, label, attn, detail, severity=severity)

    # --- Positive trust signals ---
    if identity["issuer"]["present"] and intelligence.get("issuer_status") == "ok":
        add_ok("recognized_issuer", "Recognized issuer",
               f"Recognized issuer: {identity['issuer']['value']}.")
    if identity["recipient"]["present"]:
        add_ok("recipient_extracted", "Recipient extracted",
               f"Recipient successfully extracted: {identity['recipient']['value']}.")
    if identity["issue_date"]["present"] and intelligence.get("date_status") == "ok":
        add_ok("consistent_date", "Consistent date",
               f"Issue date detected and consistent: {identity['issue_date']['value']}.")
    if identity["certificate_id"]["present"] and intelligence.get("certificate_id_status") == "ok":
        add_ok("valid_certificate_id", "Valid certificate ID",
               f"Certificate ID {identity['certificate_id']['value']} is structurally valid.")
    if float(intelligence["structure_completeness"]) >= 0.6:
        add_ok("valid_structure", "Valid certificate structure",
               f"Document structure matches the expected certificate layout "
               f"(field completeness {intelligence['structure_completeness']:.0%}).")
    if identity["course"]["present"]:
        add_ok("course_detected", "Course detected",
               f"Course detected: {identity['course']['value']}.")
    primary = intelligence["certificate_type"]["primary"]
    if primary != "unknown":
        add_ok("certificate_type_detected", "Certificate type detected",
               f"Expected certificate type detected: {primary}.")
    if identity["marks"]["present"]:
        add_ok("marks_detected", "Marks / grade present",
               "Marks and/or grade information was extracted.")

    # --- Risk signals ---
    for finding in consistency:
        severity = finding.get("severity", "medium")
        label = finding.get("label", finding["key"])
        add_risk(finding["key"], label, finding["detail"], severity=severity)

    # Unknown issuer surfaced from consistency; add a dedicated trust signal.
    if identity["issuer"]["present"] and intelligence.get("issuer_status") == "warning":
        add_risk("unknown_issuer", "Unknown issuer",
                 f"Issuer '{identity['issuer']['value']}' is not in the recognized "
                 "issuer list. Real-world issuer verification may require external "
                 "verification.", severity="medium")

    # Poor document quality.
    if not quality["text_present"]:
        add_risk("missing_text", "Missing document text",
                 "No text could be extracted from the document. It may be a "
                 "scanned image or a blank/empty document.", severity="medium")
    if quality["visual_quality"] == "attention":
        add_risk("visual_quality", "Poor visual quality",
                 "Unusual ink coverage, blank area, or color profile detected in "
                 "the document image.", severity="medium")

    # Phase 10: low extraction confidence must trigger manual review, and is
    # explicitly separated from fraud signals (missing fields are not fraud).
    extraction_confidence = extraction.extraction_confidence
    method = extraction.extraction_method or "none"
    low_confidence = (
        extraction.ocr_failed
        or not quality["text_present"]
        or (extraction_confidence is not None and extraction_confidence < 0.4)
        or method == "none"
    )
    if low_confidence:
        add_risk(
            "low_extraction_confidence", "Low extraction confidence",
            "Low extraction confidence — manual review recommended. The document "
            "could not be extracted with high confidence "
            f"(method={method}, confidence={_confidence_label(extraction_confidence)}); "
            "missing fields may be an extraction limitation rather than evidence "
            "of fraud.", severity="medium",
        )

    return {"positive": positive, "risk": risk}


def _confidence_label(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Review status (8C)
# ---------------------------------------------------------------------------

def compute_review_status(prediction: str, risk_score: float,
                          risk_signals: list[dict]) -> str:
    """Three-level review status layered on the ML prediction.

    Rules (documented + tested):
      1. prediction == 'suspicious'            -> high_risk
      2. risk_score >= HIGH_RISK_THRESHOLD     -> high_risk  (defensive)
      3. risk_score >= REVIEW_BAND_MIN         -> manual_review (elevated risk)
      4. any high-severity risk signal         -> manual_review
      5. >= MIN_MEDIUM_SIGNALS_FOR_REVIEW       -> manual_review
      6. otherwise                             -> low_risk
    """
    if prediction == "suspicious":
        return "high_risk"
    if risk_score >= HIGH_RISK_THRESHOLD:
        return "high_risk"
    if risk_score >= REVIEW_BAND_MIN:
        return "manual_review"
    high = [s for s in risk_signals if s.get("severity") == "high"]
    if high and HIGH_SIGNAL_FORCES_REVIEW:
        return "manual_review"
    medium = [s for s in risk_signals if s.get("severity") == "medium"]
    if len(medium) >= MIN_MEDIUM_SIGNALS_FOR_REVIEW:
        return "manual_review"
    return "low_risk"


REVIEW_RECOMMENDATIONS = {
    "low_risk": {
        "action": "accept",
        "heading": "Accept",
        "message": (
            "Based on the AI screening, this document shows no strong fraud-risk "
            "signals and the extracted structure is consistent. Proceed with your "
            "normal process."
        ),
    },
    "manual_review": {
        "action": "manual_review",
        "heading": "Manual review",
        "message": (
            "This document is unusual or shows elevated risk signals. Manual "
            "verification is recommended before any high-stakes decision."
        ),
    },
    "high_risk": {
        "action": "investigate",
        "heading": "High risk — investigate",
        "message": (
            "This document shows strong fraud-risk signals. Treat it as "
            "suspicious and investigate before accepting it."
        ),
    },
}


def recommended_action(review_status: str) -> dict:
    return REVIEW_RECOMMENDATIONS.get(
        review_status,
        REVIEW_RECOMMENDATIONS["manual_review"],
    )