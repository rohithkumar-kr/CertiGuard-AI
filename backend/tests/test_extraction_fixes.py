"""Tests for the PHASE 5B extraction and coverage fixes.

Covers recipient-phrase coverage, date formats, the marks-from-date bug,
issuer detection (markers, labels, title-line), the academy/academic feature
fix, expanded known-issuer coverage, and visual_blank_ratio train/runtime
semantic consistency.
"""

from PIL import Image

from app.services.extraction_service import compute_visual, extract_fields
from app.services.feature_service import build_features_from_extraction
from src.data import certificate_patterns as cp
from src.data.make_dataset import generate_dataset
from src.features.build_features import FEATURE_COLUMNS


# --------------------------------------------------------------------------
# Recipient / name extraction
# --------------------------------------------------------------------------

def test_present_this_certificate_to():
    fields = extract_fields(
        "present this certificate to Noah Berg for completing all assignments."
    )
    assert fields["candidate_name"] == "Noah Berg"


def test_pleased_to_present_this_certificate_to():
    fields = extract_fields(
        "Course Certificate\nEduStream\n"
        "We are pleased to present this certificate to Maya Patel\n"
        "for completing all assignments and assessments in Web Development."
    )
    assert fields["candidate_name"] == "Maya Patel"


def test_we_thank_name_for_participation():
    fields = extract_fields(
        "We thank Fatima Noor\nfor active participation in the Communication Skills."
    )
    assert fields["candidate_name"] == "Fatima Noor"


def test_we_thank_does_not_capture_participant():
    fields = extract_fields("We thank all participants for their engagement today.")
    assert fields["candidate_name"] is None


def test_recipient_phrase_does_not_capture_course_faculty():
    fields = extract_fields("Awarded by the course faculty for the program.")
    assert fields["candidate_name"] is None


def test_existing_awarded_to_recipient_still_works():
    fields = extract_fields("Completion Certificate\nAwarded to\nRohith Kumar K R")
    assert fields["candidate_name"] == "Rohith Kumar K R"


# --------------------------------------------------------------------------
# Date formats
# --------------------------------------------------------------------------

def test_dot_separated_yyyy_mm_dd_date():
    fields = extract_fields("Date 2025.03.02")
    assert fields["issue_date"] == "2025-03-02"


def test_dot_separated_dd_mm_yyyy_date():
    fields = extract_fields("Date of completion: 14.02.2024")
    assert fields["issue_date"] == "2024-02-14"


def test_dash_separated_dd_mm_yyyy_date():
    fields = extract_fields("Date of completion: 14-02-2024")
    assert fields["issue_date"] == "2024-02-14"


def test_slash_yyyy_mm_dd_date():
    fields = extract_fields("Date of Completion : 2025/05/19")
    assert fields["issue_date"] == "2025-05-19"


def test_month_name_date_still_works():
    assert extract_fields("Completed: September 14, 2025")["issue_date"] == "2025-09-14"
    assert extract_fields("Date of Completion: 14 September 2025")["issue_date"] == "2025-09-14"


# --------------------------------------------------------------------------
# Marks extraction context requirement
# --------------------------------------------------------------------------

def test_slash_date_is_not_marks():
    fields = extract_fields("Date of Completion : 2025/05/19")
    assert fields["marks_obtained"] is None
    assert fields["marks_total"] is None


def test_dot_date_is_not_marks():
    fields = extract_fields("Date 2025.03.02")
    assert fields["marks_obtained"] is None


def test_contextual_marks_still_extracted():
    fields = extract_fields("Marks: 95 out of 100")
    assert fields["marks_obtained"] == 95.0
    assert fields["marks_total"] == 100.0


def test_contextual_marks_with_spaced_colon():
    fields = extract_fields("Marks : 91 out of 100")
    assert fields["marks_obtained"] == 91.0
    assert fields["marks_total"] == 100.0


def test_score_label_marks():
    fields = extract_fields("Score: 85/100")
    assert fields["marks_obtained"] == 85.0
    assert fields["marks_total"] == 100.0


def test_marks_from_date_does_not_break_marks_validity():
    text = "Date of Completion : 2025/05/19\nMarks: 95 out of 100"
    fields = extract_fields(text)
    assert fields["marks_obtained"] == 95.0
    assert fields["marks_total"] == 100.0
    assert fields["issue_date"] == "2025-05-19"


# --------------------------------------------------------------------------
# Issuer extraction
# --------------------------------------------------------------------------

def test_certified_by_issuer():
    fields = extract_fields(
        "SecurEdge Labs\nTechnical Certification\n"
        "This is to certify that Ibrahim Suleiman has demonstrated proficiency in "
        "Cybersecurity and is certified by SecurEdge Labs."
    )
    assert fields["organization"] == "SecurEdge Labs"


def test_organized_by_issuer():
    fields = extract_fields(
        "Workshop Certificate\nNovaSkills\nWe thank Fatima Noor\nfor active participation.\n"
        "Organized by : NovaSkills"
    )
    assert fields["organization"] == "NovaSkills"


def test_title_line_issuer_detection():
    fields = extract_fields(
        "SecurEdge Labs\nTechnical Certification\n"
        "This is to certify that Ibrahim Suleiman has demonstrated proficiency in Cybersecurity."
    )
    assert fields["organization"] == "SecurEdge Labs"


def test_awarded_by_course_faculty_not_captured():
    fields = extract_fields("Course Certificate\nAwarded by the course faculty")
    assert fields["organization"] in ("", None)
    assert fields["organization"] != "the course faculty"


def test_online_template_uses_title_line_platform():
    text = (
        "Course Certificate\nEduStream\n"
        "We are pleased to present this certificate to Maya Patel\n"
        "for completing all assignments and assessments in Web Development.\n"
        "Date of Completion : April 3, 2024\nAwarded by the course faculty"
    )
    fields = extract_fields(text)
    assert fields["organization"] == "EduStream"
    assert fields["candidate_name"] == "Maya Patel"


def test_labeled_issuer_field():
    fields = extract_fields(
        "Certificate of Completion\nOrganization: Acme Training Ltd\n"
        "Awarded to Sarah Chen for the program."
    )
    assert fields["organization"] == "Acme Training Ltd"


# --------------------------------------------------------------------------
# Certificate type detection
# --------------------------------------------------------------------------

def test_cloudforge_academy_not_academic():
    flags = cp.certificate_type_flags(
        "CloudForge Academy\nCertification of Competency\n"
        "This is to certify that Hannah Kim has demonstrated proficiency in AWS and "
        "is certified by CloudForge Academy.",
        "CloudForge Academy",
    )
    assert flags["academic"] == 0


def test_peak_performance_academy_not_academic():
    flags = cp.certificate_type_flags(
        "Professional Training Certificate\nPeak Performance Academy\n"
        "This certifies that Lucas Ferreira has completed 40 contact hours of "
        "professional development in Leadership.",
        "Peak Performance Academy",
    )
    assert flags["academic"] == 0


def test_university_certificate_still_academic():
    flags = cp.certificate_type_flags(
        "University of Oxford\nCertificate of Achievement\n"
        "This certifies that Emma Richardson has fulfilled the requirements and was "
        "awarded the grade A.\nMarks: 91 out of 100",
        "University of Oxford",
    )
    assert flags["academic"] == 1


def test_academic_context_grade_triggers_academic():
    flags = cp.certificate_type_flags(
        "This is to certify that Anjali Rao has completed the program and was "
        "awarded the grade A."
    )
    assert flags["academic"] == 1


def test_training_vendor_academic_flag_consistency():
    features = build_features_from_extraction(_extraction_of(
        "Professional Training Certificate\nPeak Performance Academy\n"
        "This certifies that Lucas Ferreira has completed 40 contact hours of "
        "professional development in Leadership.\nCompletion date : September 3, 2024"
    ))
    assert features["certificate_type_academic"] == 0


def _extraction_of(text):
    from app.services.extraction_service import ExtractionResult
    return ExtractionResult(text=text, fields=extract_fields(text),
                            visual={"visual_blank_ratio": 0.02, "visual_sharpness": 1.0,
                                    "visual_noise": 0.02, "visual_color_anomaly": 0})


# --------------------------------------------------------------------------
# Known issuer coverage
# --------------------------------------------------------------------------

def test_expanded_known_issuers():
    assert cp.issuer_known("Imperial College London") is True
    assert cp.issuer_known("NovaSkills") is True
    assert cp.issuer_known("SecurEdge Labs") is True
    assert cp.issuer_known("CloudForge Academy") is True


def test_suspicious_issuer_still_not_known():
    assert cp.issuer_known("Online Degree Emporium") is False
    assert cp.issuer_known("Instant Cert Ltd") is False


# --------------------------------------------------------------------------
# visual_blank_ratio train/runtime semantic consistency
# --------------------------------------------------------------------------

def test_runtime_blank_page_blank_ratio_near_zero():
    blank = Image.new("RGB", (300, 300), "white")
    filled = Image.new("RGB", (300, 300), "black")
    assert compute_visual(blank)["visual_blank_ratio"] < 0.05
    assert compute_visual(filled)["visual_blank_ratio"] > 0.9


def test_training_blank_ratio_aligned_with_runtime():
    rows = generate_dataset(400, 0.30, 42)
    assert all(0.0 <= r["blank_ratio"] <= 0.15 for r in rows)


# --------------------------------------------------------------------------
# Phase 5C technical synthetic dataset generation
# --------------------------------------------------------------------------

def test_dataset_includes_technical_stratum():
    rows = generate_dataset(500, 0.30, 42)
    types = {r["certificate_type"] for r in rows}
    assert "technical" in types
    tech = [r for r in rows if r["certificate_type"] == "technical"]
    assert len(tech) >= 50
    assert {r["label"] for r in tech} == {0, 1}


def test_genuine_technical_rows_fire_technical_flag():
    rows = generate_dataset(500, 0.30, 42)
    tech_gen = [r for r in rows if r["certificate_type"] == "technical" and r["label"] == 0]
    assert tech_gen
    fired = sum(1 for r in tech_gen if cp.certificate_type_flags(
        r["text_snippet"], r["issuer"])["technical"] == 1)
    # At least 90% of genuine technical rows carry the technical-type flag
    # (a handful lose it only via label-noise flipped fraud rows).
    assert fired / len(tech_gen) >= 0.9


def test_technical_rows_use_technical_issuers():
    rows = generate_dataset(500, 0.30, 42)
    tech_gen = [r for r in rows if r["certificate_type"] == "technical" and r["label"] == 0]
    assert tech_gen
    for r in tech_gen:
        assert cp.issuer_known(r["issuer"]) is True


def test_dataset_version_is_v4():
    from src.data.make_dataset import DATASET_VERSION
    assert DATASET_VERSION == "v4"


# --------------------------------------------------------------------------
# Phase 6A workshop / attendance type detection
# --------------------------------------------------------------------------

def test_workshop_certificate_detected():
    flags = cp.certificate_type_flags(
        "Workshop Certificate\nNovaSkills\nWe thank Fatima Noor\n"
        "for active participation in the Communication Skills\n"
        "conducted on 19 June 2024 at City Convention Centre.",
        "NovaSkills",
    )
    assert flags["workshop"] == 1
    assert flags["academic"] == 0


def test_seminar_participation_certificate_detected():
    flags = cp.certificate_type_flags(
        "Seminar Participation Certificate\nLumina Professional\n"
        "We thank Tom Bakker\nfor active participation in the Leadership seminar.",
        "Lumina Professional",
    )
    assert flags["workshop"] == 1


def test_attendance_wording_detected():
    flags = cp.certificate_type_flags(
        "This is to certify that Sana Kapoor attended the Data Science workshop "
        "organized by TechEdge Training."
    )
    assert flags["workshop"] == 1


def test_completion_certificate_not_workshop():
    flags = cp.certificate_type_flags(
        "Certificate of Completion\nCogniTech Solutions\n"
        "Awarded to Sara Mitchell for successfully completing the Cloud Computing program.",
        "CogniTech Solutions",
    )
    assert flags["workshop"] == 0
    assert flags["completion"] == 1


def test_academic_certificate_not_workshop():
    flags = cp.certificate_type_flags(
        "University of Oxford\nCertificate of Achievement\nThis certifies that Emma "
        "Richardson was awarded the grade A.\nMarks: 91 out of 100",
        "University of Oxford",
    )
    assert flags["workshop"] == 0
    assert flags["academic"] == 1


def test_technical_certificate_not_workshop():
    flags = cp.certificate_type_flags(
        "Technical Certification\nSecurEdge Labs\nThis is to certify that Ibrahim "
        "Suleiman has demonstrated proficiency in Cybersecurity and is certified by "
        "SecurEdge Labs.",
        "SecurEdge Labs",
    )
    assert flags["workshop"] == 0
    assert flags["technical"] == 1


def test_workshop_certificate_also_fires_training():
    flags = cp.certificate_type_flags(
        "Workshop Certificate\nNovaSkills\nWe thank Fatima Noor for participation.",
        "NovaSkills",
    )
    assert flags["workshop"] == 1
    assert flags["training"] == 1


# --------------------------------------------------------------------------
# Phase 6B v4 synthetic dataset: workshop stratum
# --------------------------------------------------------------------------

def test_dataset_includes_workshop_stratum():
    rows = generate_dataset(500, 0.30, 42)
    types = {r["certificate_type"] for r in rows}
    assert "workshop" in types
    ws = [r for r in rows if r["certificate_type"] == "workshop"]
    assert len(ws) >= 50
    assert {r["label"] for r in ws} == {0, 1}


def test_dataset_has_six_types():
    rows = generate_dataset(600, 0.30, 42)
    counts = {}
    for r in rows:
        counts[r["certificate_type"]] = counts.get(r["certificate_type"], 0) + 1
    assert set(counts.keys()) == {
        "academic", "completion", "training", "online", "technical", "workshop",
    }
    assert len(counts) == 6


def test_genuine_workshop_rows_fire_workshop_flag():
    rows = generate_dataset(500, 0.30, 42)
    ws_gen = [r for r in rows if r["certificate_type"] == "workshop" and r["label"] == 0]
    assert ws_gen
    fired = sum(1 for r in ws_gen if cp.certificate_type_flags(
        r["text_snippet"], r["issuer"])["workshop"] == 1)
    assert fired / len(ws_gen) >= 0.9


def test_workshop_rows_use_known_issuers():
    rows = generate_dataset(500, 0.30, 42)
    ws_gen = [r for r in rows if r["certificate_type"] == "workshop" and r["label"] == 0]
    assert ws_gen
    # >=90% to allow the 5% label-noise flipped fraud rows (e.g. blank mode
    # clears the issuer), mirroring the technical-stratum test convention.
    known = sum(1 for r in ws_gen if cp.issuer_known(r["issuer"]))
    assert known / len(ws_gen) >= 0.9


def test_workshop_stratum_reproducible_seed_42():
    r1 = generate_dataset(400, 0.30, 42)
    r2 = generate_dataset(400, 0.30, 42)
    assert r1 == r2