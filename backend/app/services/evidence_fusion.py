"""Evidence fusion (Phase 12, M7 + upgrade).

Fuses independent evidence providers into a single transparent assessment:

    LIKELY_GENUINE | LIKELY_SUSPICIOUS | REQUIRES_VERIFICATION | INSUFFICIENT_EVIDENCE

and a machine-friendly 4-state decision:

    VERIFIED | REQUIRES_VERIFICATION | SUSPICIOUS | INSUFFICIENT_EVIDENCE

Design contract (Phase 12 spec + upgrade):
  * The ML model (`random_forest_v3`) is ONE evidence provider, never the
    sole arbiter. Its feature vector and threshold are never modified.
  * ML is a RISK SIGNAL, not a verdict: a high model risk alone produces
    REQUIRES_VERIFICATION (manual review), never SUSPICIOUS.
  * Evidence items are structured: source / category / signal / severity /
    confidence / explanation / status (PASS|WARNING|FAIL|UNKNOWN), plus the
    additive direction (+/-/0/?) and evidence_class
    (POSITIVE_EVIDENCE|NEGATIVE_EVIDENCE|WARNING|UNKNOWN).
  * SUSPICIOUS requires several meaningful negative signals: strong tampering,
    certificate-ID reuse, a dominating non-ML negative mass, or a high model
    risk corroborated by at least one independent negative signal.
  * When a document carries credential identifiers (verification codes) but
    no issuer-side check is possible, the result is REQUIRES_VERIFICATION —
    never VERIFIED and never SUSPICIOUS.
  * The fusion rules below encode the 15 explicit constraints (unknown issuer
    is not fraud, image-only is not fraud, OOD is not fraud, a QR's absence is
    not fraud, metadata anomalies are not fraud alone, etc.).
  * Fraud sensitivity is never reduced to make known-genuine certificates
    pass.
  * `prediction` (the ML verdict) is preserved unchanged in the API; the
    assessment is additive.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .anomaly_service import AnomalyReport
from .extraction_service import ExtractionResult
from .issuer import IssuerReport
from .pdf_forensics import ForensicReport
from .qr_service import QRReport
from .semantic_service import SemanticReport
from .tampering_service import TamperingReport
from .verification_code_service import VerificationCodeReport
from .visual_analysis import VisualReport

SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3}

STATUS_EVIDENCE_CLASS = {
    "PASS": "POSITIVE_EVIDENCE",
    "WARNING": "WARNING",
    "FAIL": "NEGATIVE_EVIDENCE",
    "UNKNOWN": "UNKNOWN",
}

STATUS_DIRECTION = {
    "PASS": "positive",
    "WARNING": "neutral",
    "FAIL": "negative",
    "UNKNOWN": "unknown",
}


@dataclass
class EvidenceItem:
    source: str
    category: str
    signal: str
    severity: str
    confidence: float
    explanation: str
    status: str = "WARNING"
    direction: str = "neutral"
    evidence_class: str = "WARNING"

    def __post_init__(self) -> None:
        if not self.direction or self.direction == "neutral":
            self.direction = STATUS_DIRECTION.get(self.status, "neutral")
        if not self.evidence_class or self.evidence_class == "WARNING":
            self.evidence_class = STATUS_EVIDENCE_CLASS.get(self.status, "WARNING")

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "category": self.category,
            "signal": self.signal,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "explanation": self.explanation,
            "status": self.status,
            "direction": self.direction,
            "evidence_class": self.evidence_class,
        }


def _item(items: list, source: str, category: str, signal: str, status: str,
          explanation: str, severity: str = "medium", confidence: float = 0.5) -> None:
    items.append(EvidenceItem(
        source=source, category=category, signal=signal, severity=severity,
        confidence=confidence, explanation=explanation, status=status,
    ))


def _append_ml_feature_analysis(items: list[EvidenceItem], features: dict,
                                risk: float, model_name: str) -> None:
    """Surface the extracted signals that pushed the ML risk score.

    Honest, feature-derived transparency: presence-style features that were
    missing (value 0) raise the score, while recovered identity signals lower
    it. No feature importance is fabricated; only actual feature values are
    described.
    """
    missing = sorted(k for k, v in features.items() if isinstance(v, (int, float)) and v == 0)
    present = sorted(k for k, v in features.items() if isinstance(v, (int, float)) and v > 0)
    _PRESENCE_KEYS = (
        "candidate_name_present", "recipient_present", "completion_date_present",
        "issue_year_valid", "date_consistency_valid", "cert_id_format_valid",
        "cert_id_checksum_valid", "issuer_known", "course_present",
        "marks_consistency_valid", "grade_consistency_valid",
    )
    key_missing = [k for k in _PRESENCE_KEYS if features.get(k) == 0]
    key_present = [k for k in _PRESENCE_KEYS if features.get(k) == 1]
    detail_bits = []
    if key_missing:
        detail_bits.append(
            "signals not present in the document: " + ", ".join(key_missing)
        )
    if key_present:
        detail_bits.append(
            "signals present: " + ", ".join(key_present)
        )
    if not detail_bits:
        detail_bits.append("no strong presence signals in the feature vector")
    status = "WARNING" if risk >= 0.3 else "PASS"
    severity = "medium" if risk >= 0.3 else "low"
    _item(items, model_name, "ML", "feature_analysis", status,
          "Model risk is driven by which signals the document actually contains: "
          + "; ".join(detail_bits) + ".",
          severity=severity, confidence=0.6)


def build_evidence(*, ml: dict, extraction: ExtractionResult, intelligence: dict,
                   semantic: SemanticReport, forensic: ForensicReport,
                   visual: VisualReport, tampering: TamperingReport,
                   qr: QRReport, issuer: IssuerReport, anomaly: AnomalyReport,
                   duplicate: dict, verification_codes: VerificationCodeReport | None = None,
                   features: dict | None = None) -> list[dict]:
    """Build the full evidence item list from every provider."""
    items: list[EvidenceItem] = []
    fields = extraction.fields or {}
    text = (extraction.text or "").strip()

    # ---- ML (random_forest_v3) ----
    # The model is a risk signal, never a verdict. A high risk is surfaced as
    # a WARNING that the fusion layer turns into REQUIRES_VERIFICATION unless
    # independent negative evidence corroborates it.
    risk = float(ml.get("risk_score") or 0.0)
    confidence = float(ml.get("confidence") or 0.5)
    prediction = ml.get("prediction")
    model_name = ml.get("model_version", "random_forest_v3")
    if prediction == "suspicious" or risk >= 0.5:
        _item(items, model_name, "ML", "risk_score",
              "WARNING", f"ML risk score {risk:.3f} exceeds the model decision "
              "threshold. High model risk is a review signal; it does not by "
              "itself prove fraud.",
              severity="high", confidence=confidence)
    elif risk >= 0.3:
        _item(items, model_name, "ML", "risk_score",
              "WARNING", f"ML risk score {risk:.3f} is elevated (above the review band).",
              severity="medium", confidence=confidence)
    else:
        _item(items, model_name, "ML", "risk_score",
              "PASS", f"ML risk score {risk:.3f} is low.",
              severity="low", confidence=confidence)

    # Transparent feature analysis: which extracted signals shaped the score.
    if features:
        _append_ml_feature_analysis(items, features, risk, model_name)

    # ---- Extraction ----
    method = extraction.extraction_method or "none"
    if extraction.ocr_failed or method == "none":
        _item(items, "extraction", "EXTRACTION", "text_source", "WARNING",
              "Text could not be extracted. This may be a scanned or "
              "unreadable document and is not treated as fraud.",
              severity="medium", confidence=0.6)
    elif not text:
        _item(items, "extraction", "EXTRACTION", "text_present", "WARNING",
              "No text content present.", severity="medium", confidence=0.5)
    else:
        _item(items, "extraction", "EXTRACTION", "text_source", "PASS",
              f"Text extracted via {'OCR' if extraction.ocr_used else method} "
              f"({len(text)} chars).", severity="low",
              confidence=extraction.extraction_confidence or 0.6)

    completeness = float(intelligence.get("structure_completeness") or 0.0)
    if completeness >= 0.6:
        _item(items, "extraction", "EXTRACTION", "field_completeness", "PASS",
              f"{completeness:.0%} of core identity fields extracted.",
              severity="low", confidence=0.7)
    elif completeness >= 0.4:
        _item(items, "extraction", "EXTRACTION", "field_completeness", "WARNING",
              f"Only {completeness:.0%} of core identity fields extracted.",
              severity="medium", confidence=0.5)
    else:
        _item(items, "extraction", "EXTRACTION", "field_completeness", "WARNING",
              "Few core identity fields could be extracted; missing fields are "
              "an extraction limitation, not fraud.", severity="medium", confidence=0.5)

    # ---- Structure ----
    primary = intelligence.get("certificate_type", {}).get("primary", "unknown")
    if primary == "unknown":
        _item(items, "intelligence", "STRUCTURE", "certificate_type", "WARNING",
              "The document does not match a recognized certificate structure.",
              severity="medium", confidence=0.5)
    else:
        _item(items, "intelligence", "STRUCTURE", "certificate_type", "PASS",
              f"Recognized certificate type: {primary}.", severity="low", confidence=0.6)

    # ---- Forensics (advisory physical structure) ----
    forensic_anomalies = forensic.anomalies or []
    if forensic_anomalies:
        for a in forensic_anomalies[:5]:
            _item(items, "pdf_forensics", "FORENSICS", a.get("key", "anomaly"),
                  "WARNING", a.get("detail", a.get("label", "forensic anomaly")),
                  severity=a.get("severity", "low"), confidence=0.4)
    elif not (forensic.signals or {}).get("not_applicable"):
        _item(items, "pdf_forensics", "FORENSICS", "physical_structure", "PASS",
              "The PDF's physical structure (metadata, fonts, xref, images) "
              "shows no anomaly indicators.", severity="low", confidence=0.6)

    # ---- Semantics ----
    if semantic.credential_statement_present:
        _item(items, "semantics", "SEMANTICS", "credential_statement", "PASS",
              "The text contains an explicit credential statement.",
              severity="low", confidence=0.7)
    else:
        _item(items, "semantics", "SEMANTICS", "credential_statement", "WARNING",
              "No explicit credential statement found in the text.",
              severity="medium", confidence=0.4)

    # ---- Consistency ----
    checks = intelligence.get("consistency_checks") or []
    findings = intelligence.get("consistency_findings") or []
    if checks:
        for c in checks:
            _item(items, "consistency", "CONSISTENCY", c.get("key", "finding"),
                  c.get("status", "WARNING"),
                  c.get("detail", c.get("label", "consistency check")),
                  severity=c.get("severity", "low"),
                  confidence=0.7 if c.get("status") == "PASS" else 0.6)
    elif findings:
        high = [f for f in findings if f.get("severity") == "high"]
        medium = [f for f in findings if f.get("severity") == "medium"]
        for f in high[:5]:
            _item(items, "consistency", "CONSISTENCY", f.get("key", "finding"), "FAIL",
                  f.get("detail", f.get("label", "inconsistency")),
                  severity="high", confidence=0.8)
        for f in medium[:5]:
            _item(items, "consistency", "CONSISTENCY", f.get("key", "finding"), "WARNING",
                  f.get("detail", f.get("label", "inconsistency")),
                  severity="medium", confidence=0.5)
        if not high and not medium:
            _item(items, "consistency", "CONSISTENCY", "internal_consistency", "PASS",
                  "No internal inconsistencies detected.", severity="low", confidence=0.7)

    # ---- Visual ----
    if visual and visual.anomalies:
        for a in visual.anomalies[:4]:
            _item(items, "visual", "VISUAL", a.get("key", "anomaly"), "WARNING",
                  a.get("detail", a.get("label", "visual anomaly")),
                  severity=a.get("severity", "low"), confidence=0.4)
    elif visual:
        _item(items, "visual", "VISUAL", "layout", "PASS",
              "Layout is clean and consistent.", severity="low", confidence=0.6)

    # ---- Tampering ----
    if tampering.status == "strong_indicators":
        _item(items, "tampering", "TAMPERING", "modification_indicators", "FAIL",
              "Multiple independent indicators suggest content modification.",
              severity="high", confidence=0.75)
    elif tampering.status == "possible":
        _item(items, "tampering", "TAMPERING", "modification_indicators", "WARNING",
              "Weak indicators of possible content modification are present.",
              severity="medium", confidence=0.4)
    elif tampering.status == "none_detected":
        _item(items, "tampering", "TAMPERING", "modification_indicators", "PASS",
              "No content-modification indicators detected.", severity="low", confidence=0.5)
    else:
        _item(items, "tampering", "TAMPERING", "modification_indicators", "UNKNOWN",
              "Content-modification analysis could not be completed.",
              severity="low", confidence=0.2)

    # ---- QR ----
    if qr.status == "verified_externally":
        _item(items, "qr", "QR", "verification_code", "PASS",
              "A QR verification code verified successfully against its target.",
              severity="medium", confidence=0.8)
    elif qr.status == "verification_page_found":
        _item(items, "qr", "QR", "verification_code", "WARNING",
              "A QR points at a verification page but it was not confirmed.",
              severity="medium", confidence=0.5)
    elif qr.status == "invalid_qr":
        _item(items, "qr", "QR", "verification_code", "WARNING",
              "A QR pattern was found but could not be decoded. Evidence only.",
              severity="medium", confidence=0.5)
    elif qr.status == "no_qr":
        _item(items, "qr", "QR", "verification_code", "UNKNOWN",
              "No QR verification code present. Absence is not evidence of fraud.",
              severity="low", confidence=0.2)
    else:
        _item(items, "qr", "QR", "verification_code", "WARNING",
              "QR verification code present but verification is unavailable.",
              severity="medium", confidence=0.5)

    # ---- Issuer ----
    iv = getattr(issuer, "issuer_verification", None)
    if iv is not None:
        # Authoritative issuer verification result from the issuer layer.
        if iv.status == "VERIFIED_BY_ISSUER":
            _item(items, "issuer", "ISSUER", "issuer_verification", "PASS",
                  f"Issuer '{iv.issuer}' was independently verified via its "
                  "official verification service.",
                  severity="medium", confidence=0.9)
        elif iv.status == "NOT_VERIFIED":
            shown = iv.checked_identifiers[0] if iv.checked_identifiers else "the credential identifier"
            _item(items, "issuer", "ISSUER", "issuer_verification", "FAIL",
                  f"The issuer's verification service reported that {shown} "
                  "could not be confirmed.",
                  severity="medium", confidence=0.8)
        elif iv.status == "VERIFICATION_UNAVAILABLE":
            _item(items, "issuer", "ISSUER", "issuer_verification", "WARNING",
                  f"Issuer '{iv.issuer}' could not be independently verified. "
                  "An unverifiable issuer is NOT evidence of fraud.",
                  severity="medium", confidence=0.5)
        else:  # ISSUER_UNKNOWN
            _item(items, "issuer", "ISSUER", "issuer_verification", "UNKNOWN",
                  "No issuer could be identified for independent verification. "
                  "An unknown issuer is NOT evidence of fraud.",
                  severity="low", confidence=0.3)
    elif issuer.status in ("known_verified", "domain_verified", "externally_verified"):
        _item(items, "issuer", "ISSUER", "verifiability", "PASS",
              f"Issuer '{issuer.issuer_name}' was independently verified "
              f"({issuer.status}).", severity="medium", confidence=0.7)
    elif issuer.status in ("extracted_but_unverified", "known_unverified"):
        _item(items, "issuer", "ISSUER", "verifiability", "WARNING",
              f"Issuer '{issuer.issuer_name}' could not be independently verified. "
              "An unverifiable issuer is NOT evidence of fraud.",
              severity="medium", confidence=0.5)
    elif issuer.status == "unknown":
        _item(items, "issuer", "ISSUER", "verifiability", "UNKNOWN",
              "No issuer could be extracted, so issuer verification is unavailable.",
              severity="low", confidence=0.3)

    # ---- Verification codes (upgrade) ----
    if verification_codes is not None:
        vc_state = verification_codes.state
        vc_count = len(verification_codes.codes)
        if vc_state == "VERIFIED_BY_ISSUER":
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "credential_identifier", "PASS",
                  f"{vc_count} credential identifier(s) positively confirmed "
                  "against the issuer-side verification service.",
                  severity="medium", confidence=0.85)
        elif vc_state == "VERIFICATION_UNAVAILABLE":
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "credential_identifier", "PASS",
                  f"{vc_count} credential identifier(s) extracted (positive "
                  "identity signal), but issuer-side verification is unavailable "
                  "in this environment. The identifiers cannot be independently "
                  "confirmed here — manual review is warranted.",
                  severity="low", confidence=0.6)
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "external_confirmation", "WARNING",
                  "The document carries verification codes that could not be "
                  "confirmed. An unconfirmed code is NOT evidence of fraud.",
                  severity="medium", confidence=0.5)
        elif vc_state == "NOT_VERIFIED":
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "credential_identifier", "PASS",
                  f"{vc_count} credential identifier(s) extracted as identity "
                  "markers.", severity="low", confidence=0.6)
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "external_confirmation", "WARNING",
                  "The credential identifiers were checked but could not be "
                  "confirmed. An unconfirmed code is NOT evidence of fraud.",
                  severity="medium", confidence=0.5)
        else:  # NO_CODE
            _item(items, "verification_code", "VERIFICATION_CODE",
                  "credential_identifier", "UNKNOWN",
                  "No credential identifier was extracted. Absence of a "
                  "verification code is NOT evidence of fraud.",
                  severity="low", confidence=0.3)

    # ---- Anomaly ----
    if anomaly.level == "high":
        _item(items, "anomaly", "ANOMALY", "anomaly_score", "WARNING",
              f"Anomaly score {anomaly.score:.2f} is high. Unusual does not mean "
              "fraudulent; manual review is warranted.",
              severity="medium", confidence=0.5)
    elif anomaly.level == "moderate":
        _item(items, "anomaly", "ANOMALY", "anomaly_score", "WARNING",
              f"Anomaly score {anomaly.score:.2f} is moderate.",
              severity="low", confidence=0.4)

    # ---- Duplicate ----
    if duplicate.get("duplicate_of"):
        dt = duplicate.get("duplicate_type")
        if dt == "cert_id":
            _item(items, "duplicate", "DUPLICATE", "duplicate", "FAIL",
                  "The same certificate ID has already been verified. Certificate "
                  "ID reuse is a strong fraud indicator.",
                  severity="high", confidence=0.9)
        else:
            _item(items, "duplicate", "DUPLICATE", "duplicate", "FAIL",
                  f"An identical document has already been verified (duplicate "
                  f"type: {dt}). Exact-file reuse warrants review.",
                  severity="medium", confidence=0.7)

    return [i.as_dict() for i in items]


# ---------------------------------------------------------------------------
# Fusion decisions
# ---------------------------------------------------------------------------

def _status_masses(items: list[dict]) -> tuple[float, float, int]:
    """Return (positive_mass, negative_mass, uncertainty_count)."""
    pos = 0.0
    neg = 0.0
    unc = 0
    for item in items:
        w = SEVERITY_WEIGHT.get(item["severity"], 1)
        conf = float(item["confidence"])
        if item["status"] == "PASS":
            pos += w * conf
        elif item["status"] == "FAIL":
            neg += w * conf
        else:
            unc += 1
    return pos, neg, unc


def _insufficient_evidence(items: list[dict], extraction: ExtractionResult) -> bool:
    if extraction.ocr_failed:
        return True
    text = (extraction.text or "").strip()
    fields = extraction.fields or {}
    core = sum(1 for k in ("candidate_name", "organization", "course", "issue_date")
               if fields.get(k))
    return not text and core == 0


def _category_status(items: list[dict]) -> dict:
    statuses: dict[str, list[str]] = {}
    for item in items:
        statuses.setdefault(item["category"], []).append(item["status"])
    out = {}
    for cat, st in statuses.items():
        if "FAIL" in st:
            out[cat] = "FAIL"
        elif "WARNING" in st or "UNKNOWN" in st:
            out[cat] = "WARNING" if "WARNING" in st else "UNKNOWN"
        else:
            out[cat] = "PASS"
    return out


def fuse(items: list[dict], *, ml: dict, extraction: ExtractionResult,
         tampering: TamperingReport, qr: QRReport, issuer: IssuerReport,
         anomaly: AnomalyReport, ood_status: str, duplicate: dict,
         verification_codes: VerificationCodeReport | None = None) -> dict:
    """Combine evidence items into the final assessment and decision."""
    pos, neg, unc = _status_masses(items)
    strong_tampering = tampering.status == "strong_indicators"
    issuer_iv = getattr(issuer, "issuer_verification", None)
    externally_verified = (
        qr.status == "verified_externally"
        or issuer.status == "externally_verified"
        or bool(issuer_iv and issuer_iv.status == "VERIFIED_BY_ISSUER")
    )
    ml_risk = float(ml.get("risk_score") or 0.0)
    ml_high = bool(ml.get("prediction") == "suspicious") or ml_risk >= 0.5
    ood_insufficient = ood_status == "insufficient_information"
    duplicate_of = duplicate.get("duplicate_of")
    duplicate_id = duplicate.get("duplicate_type") == "cert_id"

    vc = verification_codes
    vc_unavailable = bool(
        vc and vc.state in ("VERIFICATION_UNAVAILABLE", "NOT_VERIFIED")
    )
    # An issuer-side check that could not confirm the credential identifiers is
    # also an unconfirmed-verification condition (never a fraud signal by
    # itself), but only when identifiers were actually present.
    vc_unavailable = vc_unavailable or bool(
        issuer_iv
        and issuer_iv.status in ("VERIFICATION_UNAVAILABLE", "NOT_VERIFIED")
        and issuer_iv.checked_identifiers
    )
    vc_confirmed = bool(vc and vc.state == "VERIFIED_BY_ISSUER")
    external_confirmed = externally_verified or vc_confirmed

    # ---- 4-state decision (upgrade policy) ----
    if _insufficient_evidence(items, extraction) or ood_insufficient:
        decision = "INSUFFICIENT_EVIDENCE"
    elif strong_tampering:
        decision = "SUSPICIOUS"
    elif duplicate_id:
        decision = "SUSPICIOUS"
    elif external_confirmed and (ml_high or strong_tampering or neg >= 1.0):
        decision = "REQUIRES_VERIFICATION"
    elif neg >= 2.0 and neg >= pos:
        decision = "SUSPICIOUS"
    elif ml_high and neg >= 1.5:
        decision = "SUSPICIOUS"
    elif ml_high and pos >= 1.0:
        decision = "REQUIRES_VERIFICATION"
    elif vc_unavailable and (pos >= 1.5 or neg >= 1.0):
        decision = "REQUIRES_VERIFICATION"
    elif ml_high:
        decision = "REQUIRES_VERIFICATION"
    elif anomaly.level == "high" and pos >= 1.0:
        decision = "REQUIRES_VERIFICATION"
    elif pos >= 2.0 and neg < 1.0:
        if any(i["status"] == "FAIL" for i in items):
            decision = "REQUIRES_VERIFICATION"
        elif anomaly.level == "high":
            decision = "REQUIRES_VERIFICATION"
        else:
            decision = "VERIFIED"
    elif neg >= 1.0 and neg >= pos:
        decision = "REQUIRES_VERIFICATION"
    else:
        decision = "REQUIRES_VERIFICATION"

    # Legacy 4-state assessment kept for API compatibility.
    assessment = {
        "VERIFIED": "LIKELY_GENUINE",
        "REQUIRES_VERIFICATION": "REQUIRES_VERIFICATION",
        "SUSPICIOUS": "LIKELY_SUSPICIOUS",
        "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
    }[decision]

    # Confidence in the decision.
    if decision == "VERIFIED":
        confidence = min(0.95, 0.5 + (pos - neg) * 0.12)
    elif decision == "SUSPICIOUS":
        confidence = min(0.95, 0.5 + (neg - pos) * 0.12)
    else:
        confidence = max(0.4, min(0.85, 0.45 + (neg + pos) * 0.08))

    recommended_action = {
        "VERIFIED": "accept",
        "REQUIRES_VERIFICATION": "manual_verification",
        "SUSPICIOUS": "investigate",
        "INSUFFICIENT_EVIDENCE": "manual_verification",
    }[decision]

    next_action = {
        "VERIFIED": "accept",
        "REQUIRES_VERIFICATION": "manual_verification",
        "SUSPICIOUS": "investigate",
        "INSUFFICIENT_EVIDENCE": "manual_verification",
    }[decision]

    decision_summary = _decision_summary(
        decision, pos, neg, ml_high, strong_tampering, external_confirmed,
        vc_unavailable, issuer, anomaly,
    )

    return {
        "assessment": assessment,
        "decision": decision,
        "confidence": round(confidence, 3),
        "recommended_action": recommended_action,
        "next_action": next_action,
        "category_status": _category_status(items),
        "decision_summary": decision_summary,
        "summary": {
            "positive_mass": round(pos, 3),
            "negative_mass": round(neg, 3),
            "uncertainty_count": unc,
            "ml_suspicious": ml_high,
            "ml_risk_score": round(ml_risk, 3),
            "strong_tampering": strong_tampering,
            "externally_verified": external_confirmed,
            "verification_codes_state": vc.state if vc else "NO_CODE",
            "ood_status": ood_status,
            "anomaly_level": anomaly.level,
            "anomaly_score": anomaly.score,
            "duplicate": bool(duplicate_of),
        },
    }


def _decision_summary(decision: str, pos: float, neg: float, ml_high: bool,
                      strong_tampering: bool, external_confirmed: bool,
                      vc_unavailable: bool, issuer: IssuerReport,
                      anomaly: AnomalyReport) -> str:
    """A human-readable, evidence-grounded summary of the decision."""
    if decision == "VERIFIED":
        return (
            "Independent evidence across ML classification, document forensics, "
            "issuer verification and tampering analysis is consistent and "
            "supports this document. This is a preliminary automated "
            "assessment, not a legal authentication."
        )
    if decision == "SUSPICIOUS":
        reasons = []
        if strong_tampering:
            reasons.append("strong content-modification indicators")
        if neg >= 2.0:
            reasons.append("multiple independent negative signals")
        if ml_high and neg >= 1.5:
            reasons.append("a high model risk corroborated by other negative evidence")
        return (
            "Multiple independent evidence sources indicate the document should "
            "not be trusted without human review (" + "; ".join(reasons) + ")."
        )
    if decision == "INSUFFICIENT_EVIDENCE":
        return (
            "There is not enough extractable evidence to form a reliable "
            "assessment. Manual review is required."
        )
    bits = []
    if ml_high:
        bits.append("the model risk is elevated")
    if vc_unavailable:
        bits.append("credential identifiers could not be confirmed against the issuer")
    if external_confirmed:
        bits.append("strong external verification conflicts with other signals")
    if anomaly.level == "high":
        bits.append("the document is statistically unusual")
    if not bits:
        bits.append("the evidence is mixed or incomplete")
    return (
        "The evidence is contradictory or incomplete (" + "; ".join(bits) +
        "). Manual review is required before relying on this document."
    )