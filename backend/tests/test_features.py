"""Tests for feature engineering (training pipeline) and the runtime
feature service, ensuring they share one feature schema."""

import pandas as pd

from app.services.extraction_service import ExtractionResult, extract_fields
from app.services.feature_service import build_features_from_extraction
from src.data import certificate_patterns as cp
from src.features.build_features import FEATURE_COLUMNS, build_features


def _raw_df():
    return pd.DataFrame([
        {
            "cert_id": "CERT-2022-123455",
            "issuer": "University of Cambridge",
            "issue_date": "2022-06-15",
            "candidate_name": "John Walker",
            "course": "Computer Science",
            "organization": "University of Cambridge",
            "marks_total": 100,
            "marks_obtained": 95,
            "grade": "A",
            "has_signature": True,
            "has_seal": True,
            "has_qr": True,
            "has_url": False,
            "text_snippet": "This is to certify that John Walker has completed the "
                            "Computer Science program. Grade A.",
            "title": "Certificate of Achievement",
            "certificate_type": "academic",
            "blank_ratio": 0.05,
            "sharpness": 0.85,
            "noise_level": 0.05,
            "color_anomaly": 0,
            "label": 0,
        },
        {
            "cert_id": "FREECERT-2022-999999",
            "issuer": "Online Degree Emporium",
            "issue_date": "2026-12-01",
            "candidate_name": "",
            "course": "",
            "organization": "",
            "marks_total": 100,
            "marks_obtained": 150,
            "grade": "F",
            "has_signature": False,
            "has_seal": False,
            "has_qr": False,
            "has_url": True,
            "text_snippet": "Buy verified certificates online. No exam needed.",
            "title": "Certificate",
            "certificate_type": "academic",
            "blank_ratio": 0.9,
            "sharpness": 0.15,
            "noise_level": 0.5,
            "color_anomaly": 1,
            "label": 1,
        },
    ])


def test_feature_count_and_order():
    feats = build_features(_raw_df())
    assert list(feats.columns) == FEATURE_COLUMNS + ["label", "certificate_type"]
    assert len(FEATURE_COLUMNS) == 31
    assert FEATURE_COLUMNS[:22] == [
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
    ]
    assert FEATURE_COLUMNS[22:] == [
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


def test_genuine_row_features():
    feats = build_features(_raw_df())
    row = feats.iloc[0]
    assert row["cert_id_format_valid"] == 1
    assert row["cert_id_checksum_valid"] == 1
    assert row["issuer_known"] == 1
    assert row["marks_pattern_valid"] == 1
    assert row["grade_consistency_valid"] == 1
    assert row["suspicious_keyword_count"] == 0
    assert row["signature_present"] == 1
    assert row["issuer_domain_trust"] == 1.0


def test_suspicious_row_features():
    feats = build_features(_raw_df())
    row = feats.iloc[1]
    assert row["cert_id_format_valid"] == 0
    assert row["cert_id_checksum_valid"] == 0
    assert row["issuer_known"] == 0
    assert row["marks_pattern_valid"] == 0
    assert row["date_consistency_valid"] == 0
    assert row["suspicious_keyword_count"] > 0
    assert row["suspicious_url_present"] == 1
    assert row["issuer_domain_trust"] < 1.0


def test_runtime_extraction_genuine():
    text = ("University of Cambridge\nThis is to certify that John Walker "
            "has completed the Computer Science program offered by University "
            "of Cambridge and was awarded the grade A.\n"
            "Candidate ID: CERT-2022-123455\nMarks: 95 out of 100\n"
            "Issue Date: 2022-06-15\nSignature\nSeal\nQR")
    extraction = ExtractionResult(
        text=text,
        fields=extract_fields(text),
        visual={"visual_blank_ratio": 0.05, "visual_sharpness": 0.85,
                "visual_noise": 0.05, "visual_color_anomaly": 0},
    )
    features = build_features_from_extraction(extraction)
    assert set(features.keys()) == set(FEATURE_COLUMNS)
    assert extraction.fields["candidate_name"] == "John Walker"
    assert features["cert_id_format_valid"] == 1
    assert features["issuer_known"] == 1
    assert features["grade_consistency_valid"] == 1
    assert features["candidate_name_present"] == 1


def test_runtime_extraction_missing_values():
    extraction = ExtractionResult(text="", fields={}, visual={})
    features = build_features_from_extraction(extraction)
    assert set(features.keys()) == set(FEATURE_COLUMNS)
    assert features["candidate_name_present"] == 0
    assert features["organization_present"] == 0
    assert features["marks_pattern_valid"] == 0
    assert 0.0 <= features["visual_blank_ratio"] <= 1.0


def test_runtime_extraction_invalid_marks():
    extraction = ExtractionResult(
        text="",
        fields={"marks_total": "abc", "marks_obtained": "xyz", "grade": None},
        visual={},
    )
    features = build_features_from_extraction(extraction)
    assert features["marks_pattern_valid"] == 0
    assert features["grade_consistency_valid"] == 0


def test_runtime_extraction_suspicious_text():
    extraction = ExtractionResult(text="Buy verified certificates online. No exam needed.")
    features = build_features_from_extraction(extraction)
    assert features["suspicious_keyword_count"] > 0
    assert features["suspicious_url_present"] == 0  # no URL marker present


def test_runtime_and_training_feature_order_match():
    extraction = ExtractionResult(text="")
    runtime = build_features_from_extraction(extraction)
    assert list(runtime.keys()) == FEATURE_COLUMNS


def test_grade_band_and_consistency_helpers():
    assert cp.grade_band(95) == "A"
    assert cp.grade_band(50) == "D"
    assert cp.grade_consistent("A", 95) is True
    assert cp.grade_consistent("C", 95) is False


# --------------------------------------------------------------------------
# v2 generalized extraction patterns
# --------------------------------------------------------------------------

def test_extract_awarded_to_recipient():
    fields = extract_fields("Completion Certificate\nAwarded to\nRohith Kumar K R")
    assert fields["candidate_name"] == "Rohith Kumar K R"


def test_extract_presented_to_recipient():
    fields = extract_fields("Presented to Priya Nair upon completion of the program.")
    assert fields["candidate_name"] == "Priya Nair"


def test_extract_month_day_year_date():
    fields = extract_fields("Completed: September 14, 2025")
    assert fields["issue_date"] == "2025-09-14"


def test_extract_day_month_year_date():
    fields = extract_fields("Date of Completion: 14 September 2025")
    assert fields["issue_date"] == "2025-09-14"


def test_extract_dd_mm_yyyy_date():
    fields = extract_fields("Issue Date: 14/09/2025")
    assert fields["issue_date"] == "2025-09-14"


def test_extract_completion_title_and_type():
    text = ("AWS Training & Certification\nDirector, AWS Training & Certification\n"
            "Securely Connecting AWS IoT Devices to the Cloud\n"
            "Completed: September 14, 2025\n"
            "Completion Certificate\nAwarded to\nRohith Kumar K R")
    extraction = ExtractionResult(
        text=text,
        fields=extract_fields(text),
        visual={"visual_blank_ratio": 0.02, "visual_sharpness": 1.0,
                "visual_noise": 0.02, "visual_color_anomaly": 0},
    )
    features = build_features_from_extraction(extraction)
    assert extraction.fields["certificate_title"] == "Completion Certificate"
    assert features["certificate_type_academic"] == 0
    assert features["certificate_type_completion"] == 1
    assert features["certificate_type_training"] == 1
    assert features["recipient_present"] == 1
    assert features["completion_date_present"] == 1
    assert features["completion_title_present"] == 1
    assert features["candidate_name_present"] == 1
    assert features["course_present"] == 1


def test_extract_corporate_issuer_via_marker():
    text = ("CogniTech Solutions\nCertificate of Completion\n"
            "Presented to Liam Brown for successfully completing the Cloud Computing "
            "program offered by CogniTech Solutions.\nDate of completion: 14/03/2024")
    extraction = ExtractionResult(
        text=text,
        fields=extract_fields(text),
        visual={"visual_blank_ratio": 0.02, "visual_sharpness": 0.9,
                "visual_noise": 0.02, "visual_color_anomaly": 0},
    )
    features = build_features_from_extraction(extraction)
    assert extraction.fields["organization"] == "CogniTech Solutions"
    assert features["issuer_present"] == 1
    assert features["organization_present"] == 1
    assert features["certificate_structure_completeness"] == 1.0


def test_runtime_schema_matches_training_schema_v2():
    import pandas as pd
    raw = _raw_df()
    training = build_features(raw)
    extraction = ExtractionResult(
        text="Completion Certificate\nAwarded to Rohith Kumar K R\nCompleted: 2025-09-14",
        fields=extract_fields("Completion Certificate\nAwarded to Rohith Kumar K R\nCompleted: 2025-09-14"),
        visual={},
    )
    runtime = build_features_from_extraction(extraction)
    assert list(runtime.keys()) == FEATURE_COLUMNS
    assert list(training.columns[:len(FEATURE_COLUMNS)]) == FEATURE_COLUMNS
    assert len(FEATURE_COLUMNS) == 31


# --------------------------------------------------------------------------
# Phase 5C technical certificate features
# --------------------------------------------------------------------------

TECHNICAL_TEXT = (
    "SecurEdge Labs\nTechnical Certification\n"
    "This is to certify that Ibrahim Suleiman has demonstrated proficiency in "
    "Cybersecurity and is certified by SecurEdge Labs.\n"
    "Certification code : TECH-2024-0881\n"
    "Date of Certification : 11 November 2024\nVerification code embedded"
)


def test_technical_certificate_detected():
    flags = cp.certificate_type_flags(TECHNICAL_TEXT, "SecurEdge Labs")
    assert flags["technical"] == 1
    assert flags["academic"] == 0


def test_technical_flag_in_training_features():
    raw = _raw_df()
    raw.loc[0, "certificate_type"] = "technical"
    raw.loc[0, "title"] = "Technical Certification"
    raw.loc[0, "text_snippet"] = TECHNICAL_TEXT
    feats = build_features(raw)
    assert feats.iloc[0]["certificate_type_technical"] == 1
    assert feats.iloc[1]["certificate_type_technical"] == 0


def test_technical_flag_in_runtime_features():
    extraction = ExtractionResult(
        text=TECHNICAL_TEXT,
        fields=extract_fields(TECHNICAL_TEXT),
        visual={"visual_blank_ratio": 0.02, "visual_sharpness": 1.0,
                "visual_noise": 0.02, "visual_color_anomaly": 0},
    )
    features = build_features_from_extraction(extraction)
    assert features["certificate_type_technical"] == 1
    assert features["certificate_type_academic"] == 0


def test_technical_flag_not_fired_for_plain_completion():
    text = ("CogniTech Solutions\nCertificate of Completion\n"
            "Presented to Liam Brown for successfully completing the Cloud Computing "
            "program offered by CogniTech Solutions.\nDate of completion: 14/03/2024")
    flags = cp.certificate_type_flags(text, "CogniTech Solutions")
    assert flags["technical"] == 0
    assert flags["completion"] == 1


def test_technical_flag_not_fired_for_workshop():
    text = ("Workshop Certificate\nNovaSkills\nWe thank Fatima Noor\n"
            "for active participation in the Communication Skills conducted on 19 June 2024.")
    flags = cp.certificate_type_flags(text, "NovaSkills")
    assert flags["technical"] == 0


def test_technical_flag_not_fired_for_academic_engineering():
    text = ("MIT\nDegree Certificate\nThis certifies that John Walker completed the "
            "Electrical Engineering program and was awarded the grade A.\nMarks: 95 out of 100")
    flags = cp.certificate_type_flags(text, "MIT")
    assert flags["technical"] == 0
    assert flags["academic"] == 1


def test_technology_word_alone_is_not_technical():
    text = "Certificate of Attendance for the Technology Awareness Seminar at Lumina Professional."
    flags = cp.certificate_type_flags(text, "Lumina Professional")
    assert flags["technical"] == 0