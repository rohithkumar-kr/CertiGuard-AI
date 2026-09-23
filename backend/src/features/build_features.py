"""Feature engineering: raw synthetic certificate records -> feature matrix.

Every row becomes a fixed set of numeric features shared with runtime
extraction (app/services/feature_service.py), so training and inference
always use the same schema.

Output: CSV at data/processed/features.csv
"""

import argparse
import os
from datetime import datetime, date

import pandas as pd

from src.data import certificate_patterns as cp

FEATURE_SCHEMA_VERSION = "v3"

FEATURE_COLUMNS = [
    "cert_id_format_valid",
    "cert_id_checksum_valid",
    "issuer_known",
    "issue_year_valid",
    "date_consistency_valid",
    "candidate_name_present",
    "course_present",
    "organization_present",
    "text_field_completeness",
    "marks_pattern_valid",
    "grade_consistency_valid",
    "suspicious_keyword_count",
    "suspicious_url_present",
    "signature_present",
    "seal_present",
    "qr_present",
    "visual_blank_ratio",
    "visual_sharpness",
    "visual_noise",
    "visual_color_anomaly",
    "text_duplicate_similarity",
    "issuer_domain_trust",
    # --- v2 generalized certificate features ---
    "certificate_type_academic",
    "certificate_type_completion",
    "certificate_type_training",
    "certificate_type_technical",
    "recipient_present",
    "completion_date_present",
    "issuer_present",
    "completion_title_present",
    "certificate_structure_completeness",
]


def _parse_date(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value)).date()
    except (ValueError, TypeError):
        return None


def date_consistency_valid(issue_date: date, issue_year_valid: bool) -> bool:
    if issue_date is None or not issue_year_valid:
        return False
    return issue_date <= date.today()


def issuer_domain_trust(issuer: str) -> float:
    if cp.issuer_known(issuer):
        return 1.0
    if not issuer or not issuer.strip():
        return 0.0
    text = issuer.lower()
    if any(w in text for w in ["emporium", "sale", "fast", "instant", "online degree", "grade 4 sale", "diploma"]):
        return 0.15
    return 0.4


def _as_text(value) -> str:
    """Coerce a raw cell to text, treating pandas NaN / None as empty."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        cert_id = _as_text(r.get("cert_id"))
        issuer = _as_text(r.get("issuer"))
        name = _as_text(r.get("candidate_name"))
        course = _as_text(r.get("course"))
        organization = _as_text(r.get("organization"))
        title = _as_text(r.get("title"))
        text = _as_text(r.get("text_snippet"))
        issue_date = _parse_date(r.get("issue_date"))
        year = issue_date.year if issue_date else None
        year_valid = cp.issue_year_valid(year)
        date_valid = date_consistency_valid(issue_date, year_valid)

        marks_total = r.get("marks_total")
        marks_obtained = r.get("marks_obtained")
        try:
            total = float(marks_total)
            obtained = float(marks_obtained)
            marks_valid = total > 0 and 0 <= obtained <= total
            pct = (obtained / total * 100) if total > 0 else 0.0
        except (TypeError, ValueError):
            marks_valid = False
            pct = 0.0

        grade = str(r.get("grade") or "")
        grade_valid = cp.grade_consistent(grade, pct)

        present = [name, course, organization, issuer]
        completeness = sum(1 for p in present if p and p.strip()) / len(present)

        try:
            blank = float(r.get("blank_ratio") or 0.0)
        except (TypeError, ValueError):
            blank = 0.0
        try:
            sharpness = float(r.get("sharpness") or 0.0)
        except (TypeError, ValueError):
            sharpness = 0.0
        try:
            noise = float(r.get("noise_level") or 0.0)
        except (TypeError, ValueError):
            noise = 0.0

        # --- v2 generalized features (mirror runtime feature_service) ---
        recipient_ok = bool(name and name.strip() and len(name.strip()) > 3)
        date_ok = issue_date is not None
        issuer_ok = bool((issuer or organization) and str(issuer or organization).strip())
        title_ok = bool(title and title.strip())
        type_flags = cp.certificate_type_flags(text or "", issuer or "")
        structure_parts = [recipient_ok, date_ok, issuer_ok, title_ok]
        structure = round(sum(1 for p in structure_parts if p) / len(structure_parts), 4)

        rows.append({
            "cert_id_format_valid": int(cp.cert_id_format_valid(cert_id)),
            "cert_id_checksum_valid": int(cp.cert_id_checksum_valid(cert_id)),
            "issuer_known": int(cp.issuer_known(issuer)),
            "issue_year_valid": int(year_valid),
            "date_consistency_valid": int(date_valid),
            "candidate_name_present": int(bool(name and name.strip() and len(name.strip()) > 3)),
            "course_present": int(bool(course and course.strip())),
            "organization_present": int(bool(organization and organization.strip())),
            "text_field_completeness": completeness,
            "marks_pattern_valid": int(marks_valid),
            "grade_consistency_valid": int(grade_valid),
            "suspicious_keyword_count": cp.suspicious_keyword_count(text),
            "suspicious_url_present": int(cp.suspicious_url_present(text) or bool(r.get("has_url"))),
            "signature_present": int(bool(r.get("has_signature"))),
            "seal_present": int(bool(r.get("has_seal"))),
            "qr_present": int(bool(r.get("has_qr"))),
            "visual_blank_ratio": blank,
            "visual_sharpness": sharpness,
            "visual_noise": noise,
            "visual_color_anomaly": int(r.get("color_anomaly") or 0),
            "text_duplicate_similarity": 0.0,
            "issuer_domain_trust": issuer_domain_trust(issuer),
            # --- v2 generalized features ---
            "certificate_type_academic": int(type_flags["academic"]),
            "certificate_type_completion": int(type_flags["completion"]),
            "certificate_type_training": int(type_flags["training"]),
            "certificate_type_technical": int(type_flags["technical"]),
            "recipient_present": int(recipient_ok),
            "completion_date_present": int(date_ok),
            "issuer_present": int(issuer_ok),
            "completion_title_present": int(title_ok),
            "certificate_structure_completeness": structure,
            "label": int(r.get("label") or 0),
            "certificate_type": str(r.get("certificate_type") or "unknown"),
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Build feature matrix from raw dataset")
    parser.add_argument("--input", default=os.environ.get("DATA_RAW_DIR", "./data/raw/certificates.csv"))
    parser.add_argument("--output", default=os.environ.get("DATA_PROCESSED_DIR", "./data/processed/features.csv"))
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    feats = build_features(df)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    feats.to_csv(args.output, index=False)
    print(f"Wrote {len(feats)} rows x {len(feats.columns)} cols to {args.output}")


if __name__ == "__main__":
    main()
