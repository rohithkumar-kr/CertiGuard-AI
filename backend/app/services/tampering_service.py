"""Tampering detection (Phase 12, M2).

Combines PDF-forensics and visual-analysis evidence into an advisory
``tampering_status``:

    none_detected | possible | strong_indicators | unable_to_determine

The status only *raises* suspicion (it feeds the evidence fusion layer). It
never, on its own, declares a certificate fraudulent. All signals are generic
and issuer-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .pdf_forensics import ForensicReport
from .visual_analysis import VisualReport


@dataclass
class TamperingReport:
    status: str = "unable_to_determine"
    signals: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)


def _forensic_severity_map(key: str) -> str:
    mapping = {
        "pdf_encrypted": "medium",
        "pdf_repaired": "medium",
        "incremental_update": "low",
        "metadata_date_inconsistent": "medium",
        "metadata_future_date": "low",
        "scan_with_text_producer": "low",
    }
    return mapping.get(key, "low")


def assess_tampering(forensic: ForensicReport, visual: VisualReport,
                     metadata: dict | None = None) -> TamperingReport:
    """Combine forensic + visual evidence into an advisory tampering status.

    ``metadata`` is the extraction metadata dict (method, ocr flags, etc.) so
    that image-only documents are not penalized for being image-only.
    """
    report = TamperingReport()
    findings = report.findings
    signals = report.signals

    if forensic.signals.get("error") or visual.signals.get("error"):
        return report  # unable_to_determine

    # --- Forensic-based findings ---
    f_seen = set()
    for anomaly in forensic.anomalies:
        f_seen.add(anomaly["key"])
        findings.append({
            "source": "pdf_forensics",
            "kind": anomaly["key"],
            "label": anomaly["label"],
            "severity": _forensic_severity_map(anomaly["key"]),
            "detail": anomaly["detail"],
        })

    # Multiple different image compression filters inside one page can hint at
    # pasted content. Advisory only.
    comps = set(forensic.signals.get("image_compressions") or [])
    if len(comps) > 1:
        findings.append({
            "source": "pdf_forensics",
            "kind": "mixed_compression",
            "label": "Mixed image compression",
            "severity": "medium",
            "detail": f"Page embeds images with different encodings: {sorted(comps)}.",
        })
        signals["mixed_compression"] = True

    img_res = forensic.signals.get("image_resolutions") or []
    if img_res:
        widths = [r[0] for r in img_res if r[0]]
        if widths and (max(widths) / max(1, min(widths))) > 6:
            findings.append({
                "source": "pdf_forensics",
                "kind": "resolution_inconsistency",
                "label": "Inconsistent image resolution",
                "severity": "low",
                "detail": "Embedded images span a wide range of resolutions.",
            })
            signals["resolution_inconsistency"] = True

    # --- Visual-based findings ---
    for anomaly in visual.anomalies:
        findings.append({
            "source": "visual",
            "kind": anomaly["key"],
            "label": anomaly["label"],
            "severity": anomaly["severity"],
            "detail": anomaly["detail"],
        })

    # --- Metadata / extraction context ---
    extraction_method = (metadata or {}).get("method")
    is_image_only = bool(extraction_method == "ocr" or (metadata or {}).get("ocr_used"))
    signals["image_only_context"] = is_image_only
    signals["extraction_method"] = extraction_method

    # --- Decide status ---
    severity_score = {"low": 1, "medium": 2, "high": 3}
    strong = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    strong_kinds = {f["kind"] for f in strong}
    medium_kinds = {f["kind"] for f in medium}

    # Strong indicators: genuinely adversarial patterns that rarely appear in
    # legitimate documents (repaired PDF + duplicated region + mixed
    # compression together).
    duplicated = "duplicated_region" in medium_kinds or "duplicated_region" in strong_kinds
    repaired = "pdf_repaired" in medium_kinds
    mixed = signals.get("mixed_compression", False)

    if strong_kinds:
        report.status = "strong_indicators"
    elif duplicated and mixed:
        report.status = "strong_indicators"
    elif (duplicated or repaired or mixed) and len(medium) >= 2:
        report.status = "possible"
    elif medium_kinds or strong_kinds:
        report.status = "possible"
    else:
        report.status = "none_detected"

    signals["finding_count"] = len(findings)
    return report