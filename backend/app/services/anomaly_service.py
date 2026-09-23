"""Anomaly scoring (Phase 12, M6).

Computes an independent, document-agnostic anomaly score (0..1) from multiple
layers of evidence (extraction quality, structure, visual, PDF forensics,
issuer verifiability, consistency, tampering).

CONTRACT (Phase 12 spec):
  * the anomaly score NEVER modifies the ML feature vector or prediction;
  * OOD / unknown issuer / image-only / missing fields / metadata quirks may
    raise the score but are NOT evidence of fraud;
  * the score is a *review-routing* signal (used by the evidence fusion layer
    to decide between LIKELY_GENUINE and REQUIRES_VERIFICATION), never a
    suspicion verdict on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .extraction_service import ExtractionResult
from .issuer import IssuerReport
from .pdf_forensics import ForensicReport
from .tampering_service import TamperingReport
from .visual_analysis import VisualReport


@dataclass
class AnomalyReport:
    score: float = 0.0
    level: str = "low"  # low | moderate | high
    contributors: list = field(default_factory=list)


def _contrib(c: list, key: str, label: str, value: float, detail: str) -> None:
    c.append({
        "key": key, "label": label, "value": round(float(value), 3),
        "detail": detail,
    })


def compute_anomaly(extraction: ExtractionResult, intelligence: dict,
                    features: dict, forensic: ForensicReport | None = None,
                    visual: VisualReport | None = None,
                    tampering: TamperingReport | None = None,
                    issuer: IssuerReport | None = None) -> AnomalyReport:
    """Aggregate anomaly contributors into a single advisory score."""
    report = AnomalyReport()
    contribs = []
    parts = []

    # --- Extraction quality ---
    method = extraction.extraction_method or "none"
    conf = extraction.extraction_confidence
    text = (extraction.text or "").strip()
    if extraction.ocr_failed or method == "none":
        parts.append((1.0, 0.35))
        _contrib(contribs, "extraction_failed", "Extraction failed", 1.0,
                 "No reliable text could be extracted.")
    elif not text:
        parts.append((0.6, 0.3))
        _contrib(contribs, "no_text", "No text", 0.6,
                 "No text present after extraction.")
    elif conf is not None and conf < 0.4:
        parts.append((0.55, 0.3))
        _contrib(contribs, "low_confidence", "Low extraction confidence", 0.55,
                 f"Extraction confidence {conf:.2f}.")
    elif conf is not None and conf < 0.7:
        parts.append((0.25, 0.25))
        _contrib(contribs, "medium_confidence", "Medium extraction confidence", 0.25,
                 f"Extraction confidence {conf:.2f}.")
    elif method == "ocr":
        # OCR is a valid method; image-only is not an anomaly by itself.
        parts.append((0.1, 0.15))
        _contrib(contribs, "ocr_method", "OCR text source", 0.1,
                 "Text was recovered via OCR; expected for scanned certificates.")

    # --- Structure ---
    structure = float(intelligence.get("structure_completeness") or 0.0)
    primary = intelligence.get("certificate_type", {}).get("primary", "unknown")
    if primary == "unknown":
        parts.append((0.7, 0.25))
        _contrib(contribs, "unknown_type", "Unrecognized certificate type", 0.7,
                 "The document does not match any expected certificate pattern.")
    if structure < 0.4:
        parts.append((0.65, 0.25))
        _contrib(contribs, "low_structure", "Low structural completeness", 0.65,
                 f"Field completeness {structure:.0%}.")
    elif structure < 0.6:
        parts.append((0.3, 0.2))
        _contrib(contribs, "partial_structure", "Partial structure", 0.3,
                 f"Field completeness {structure:.0%}.")

    # --- Consistency findings ---
    findings = intelligence.get("consistency_findings") or []
    high = [f for f in findings if f.get("severity") == "high"]
    medium = [f for f in findings if f.get("severity") == "medium"]
    if high:
        parts.append((0.75, 0.3))
        _contrib(contribs, "high_consistency_findings", "High-severity findings", 0.75,
                 f"{len(high)} high-severity internal inconsistency findings.")
    elif medium:
        parts.append((0.35, 0.2))
        _contrib(contribs, "medium_consistency_findings", "Medium-severity findings", 0.35,
                 f"{len(medium)} medium-severity internal inconsistency findings.")

    # --- Visual ---
    if visual and visual.signals.get("edge_alignment_consistency") is not None:
        if visual.signals["edge_alignment_consistency"] < 0.65:
            parts.append((0.6, 0.15))
            _contrib(contribs, "alignment", "Alignment anomaly", 0.6,
                     "Text layout is not axis-aligned.")
    if visual:
        anomaly_keys = {a["key"] for a in visual.anomalies}
        if "duplicated_region" in anomaly_keys:
            parts.append((0.6, 0.2))
            _contrib(contribs, "duplicated_region", "Duplicated region", 0.6,
                     "Near-identical visual regions detected.")

    # --- PDF forensics ---
    if forensic:
        sev = {"low": 1, "medium": 2, "high": 3}
        f_score = min(1.0, sum(sev.get(a.get("severity"), 1) for a in forensic.anomalies) * 0.25)
        if f_score > 0:
            parts.append((f_score, 0.15))
            _contrib(contribs, "forensics", "PDF structural anomalies", f_score,
                     f"{len(forensic.anomalies)} PDF forensics flags.")

    # --- Issuer verifiability ---
    if issuer:
        if issuer.status == "unknown":
            parts.append((0.4, 0.1))
            _contrib(contribs, "issuer_unknown", "Issuer not extracted", 0.4,
                     "No issuer could be extracted.")
        elif issuer.status == "extracted_but_unverified":
            parts.append((0.25, 0.1))
            _contrib(contribs, "issuer_unverified", "Issuer unverified", 0.25,
                     "Issuer could not be independently verified.")
        elif issuer.status == "known_unverified":
            parts.append((0.15, 0.1))
            _contrib(contribs, "issuer_unverified", "Issuer unverified", 0.15,
                     "Issuer known but not externally verified.")

    # --- Tampering (advisory; strong indicators feed suspicion separately) ---
    if tampering and tampering.status == "strong_indicators":
        parts.append((0.7, 0.2))
        _contrib(contribs, "tampering_indicators", "Tampering indicators", 0.7,
                 "Multiple independent indicators of content modification.")
    elif tampering and tampering.status == "possible":
        parts.append((0.35, 0.15))
        _contrib(contribs, "tampering_possible", "Possible tampering", 0.35,
                 "Weak tampering-related indicators present.")

    # --- Blend contributors (weighted mean) ---
    if parts:
        weight_sum = sum(w for _, w in parts)
        score = sum(v * w for v, w in parts) / weight_sum
    else:
        score = 0.0
    report.score = round(score, 4)
    report.level = "high" if score >= 0.6 else "moderate" if score >= 0.35 else "low"
    report.contributors = contribs
    return report