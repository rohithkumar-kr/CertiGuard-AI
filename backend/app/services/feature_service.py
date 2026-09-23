"""Build the fixed ML feature vector from an extraction result.

Mirrors src/features/build_features.py so training and runtime inference use
identical feature semantics. Missing values degrade to neutral defaults
instead of failing.
"""

from datetime import date, datetime

from src.data import certificate_patterns as cp
from src.features.build_features import issuer_domain_trust

from app.services.extraction_service import ExtractionResult
from app.core.logging import get_logger

logger = get_logger("feature_service")

DEFAULT_VISUAL = {
    "visual_blank_ratio": 0.0,
    "visual_sharpness": 0.0,
    "visual_noise": 0.0,
    "visual_color_anomaly": 0,
}


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _fraction_present(values) -> float:
    if not values:
        return 0.0
    return sum(1 for v in values if v and str(v).strip()) / len(values)


def build_features_from_extraction(extraction: ExtractionResult) -> dict:
    fields = extraction.fields or {}
    visual = {**DEFAULT_VISUAL, **(extraction.visual or {})}

    cert_id = fields.get("cert_id")
    organization = fields.get("organization")
    candidate_name = fields.get("candidate_name")
    course = fields.get("course")
    issue_date = _parse_date(fields.get("issue_date"))
    year = issue_date.year if issue_date else None
    year_valid = cp.issue_year_valid(year)

    date_valid = False
    if issue_date is not None and year_valid:
        date_valid = issue_date <= date.today()

    try:
        total = float(fields.get("marks_total"))
        obtained = float(fields.get("marks_obtained"))
        marks_valid = total > 0 and 0 <= obtained <= total
        pct = (obtained / total * 100) if total > 0 else 0.0
    except (TypeError, ValueError):
        marks_valid = False
        pct = 0.0

    grade = fields.get("grade")
    grade_valid = cp.grade_consistent(grade, pct) if grade else False

    text = extraction.text or ""

    # --- v2 generalized certificate features (mirror src/features/build_features.py) ---
    recipient_ok = bool(candidate_name and str(candidate_name).strip())
    date_ok = issue_date is not None
    issuer_ok = bool(organization and str(organization).strip())
    title_ok = bool(fields.get("certificate_title") and str(fields.get("certificate_title")).strip())
    type_flags = cp.certificate_type_flags(text, organization or "")
    structure_parts = [recipient_ok, date_ok, issuer_ok, title_ok]
    structure = round(sum(1 for p in structure_parts if p) / len(structure_parts), 4)

    features = {
        "cert_id_format_valid": int(cp.cert_id_format_valid(cert_id or "")),
        "cert_id_checksum_valid": int(cp.cert_id_checksum_valid(cert_id or "")),
        "issuer_known": int(cp.issuer_known(organization or "")),
        "issue_year_valid": int(year_valid),
        "date_consistency_valid": int(date_valid),
        "candidate_name_present": int(bool(candidate_name and str(candidate_name).strip())),
        "course_present": int(bool(course and str(course).strip())),
        "organization_present": int(bool(organization and str(organization).strip())),
        "text_field_completeness": round(_fraction_present([candidate_name, course, organization]), 4),
        "marks_pattern_valid": int(marks_valid),
        "grade_consistency_valid": int(grade_valid),
        "suspicious_keyword_count": cp.suspicious_keyword_count(text),
        "suspicious_url_present": int(cp.suspicious_url_present(text)),
        "signature_present": int(bool(fields.get("has_signature"))),
        "seal_present": int(bool(fields.get("has_seal"))),
        "qr_present": int(bool(fields.get("has_qr"))),
        "visual_blank_ratio": float(visual.get("visual_blank_ratio", 0.0)),
        "visual_sharpness": float(visual.get("visual_sharpness", 0.0)),
        "visual_noise": float(visual.get("visual_noise", 0.0)),
        "visual_color_anomaly": int(visual.get("visual_color_anomaly", 0)),
        "text_duplicate_similarity": 0.0,
        "issuer_domain_trust": issuer_domain_trust(organization or ""),
        # --- v2 generalized certificate features ---
        "certificate_type_academic": int(type_flags["academic"]),
        "certificate_type_completion": int(type_flags["completion"]),
        "certificate_type_training": int(type_flags["training"]),
        "certificate_type_technical": int(type_flags["technical"]),
        "recipient_present": int(recipient_ok),
        "completion_date_present": int(date_ok),
        "issuer_present": int(issuer_ok),
        "completion_title_present": int(title_ok),
        "certificate_structure_completeness": structure,
    }
    return features
