"""Generate a synthetic, reproducible certificate dataset for the prototype.

This is NOT real data. It models plausible certificate records (genuine and
fraudulent patterns) so a fraud-risk classifier can be trained and the full
MLOps pipeline demonstrated without a real (and unavailable) labeled dataset.

Dataset generation process (v4)
-------------------------------
The dataset is built in six certificate-type strata, each containing genuine
(label=0) and fraudulent (label=1) examples:

  A) academic   - university degree / achievement certificates. Structured
                  like v1: CERT-YYYY-XXXXXX ids with checksum, marks & grade,
                  "certify that" recipient, signature/seal/QR markers, issuer
                  drawn from KNOWN_ISSUERS.
  B) completion - corporate / professional course-completion certificates.
                  "Awarded to"/"Presented to" recipient, completion titles,
                  multiple date formats, no marks/grade, corporate issuers
                  (both marker-based and title-only so runtime extraction
                  behaviour matches the structured columns).
  C) training   - professional-training certificates (training titles,
                  corporate/academy issuers, date + recipient present).
  D) online     - online course-completion certificates (course certificates,
                  "awarded to" phrasing, "Month DD, YYYY" dates).
  E) technical  - vendor technical-certification certificates added in Phase
                  5C: TECH-YYYY-NNNN codes, "certified by" / "demonstrated
                  proficiency" / "competency" phrasing, technical subject
                  domains (cloud, security, AWS, data science, ...), no
                  marks/grade, technical vendor issuers. Structurally distinct
                  from the frozen external-validation technical PDFs.
  F) workshop   - workshop / attendance certificates added in Phase 6A/6B:
                  "Workshop Certificate" / "Certificate of Attendance" /
                  "Seminar Participation Certificate" titles, "We thank ... for
                  active participation" wording, "organized by" issuer marker,
                  no marks/grade, low-stakes attendance semantics.

Fraudulent examples across every type inject 1-3 of the same violation modes
as v1 (suspicious marketing text, future dates, unknown issuers, blank
documents, URLs, poor visuals, malformed ids), plus technical-specific modes
(invalid certification codes, altered names, missing certification context)
and workshop-specific modes (invalid workshop codes, missing event/attendance
context), so the model learns fraud signals that generalise across document
types instead of per-type.

Reproducibility: a fixed seed (default 42) drives all randomness. Class
balance is maintained globally (default 30% fraudulent) and per type. 5%
label noise is applied so the problem is not trivially separable.

Output: CSV at data/raw/certificates.csv with columns:
  cert_id, issuer, issue_date, candidate_name, course, organization,
  marks_total, marks_obtained, grade, has_signature, has_seal, has_qr,
  has_url, text_snippet, title, certificate_type, blank_ratio, sharpness,
  noise_level, color_anomaly, label
"""

import argparse
import os
import random
from datetime import datetime, timezone

from src.data import certificate_patterns as cp

DATASET_VERSION = "v4"

FIRST_NAMES = [
    "Aarav", "Priya", "Liam", "Emma", "Noah", "Olivia", "Ethan", "Ava",
    "Lucas", "Mia", "Vihaan", "Ananya", "Ishaan", "Diya", "Kabir", "Sana",
    "Rohan", "Meera", "Arjun", "Zara", "Daniel", "Sofia", "Mateo", "Amara",
]

LAST_NAMES = [
    "Sharma", "Patel", "Johnson", "Smith", "Garcia", "Lee", "Kumar", "Iyer",
    "Singh", "Chen", "Brown", "Davis", "Wilson", "Nair", "Gupta", "Reddy",
    "Desai", "Rao", "Kapoor", "Menon", "Walker", "Young", "Miller", "White",
]

COURSES = [
    "Computer Science", "Electrical Engineering", "Mechanical Engineering",
    "Business Administration", "Data Science", "Artificial Intelligence",
    "Civil Engineering", "MBA", "Biotechnology", "Economics",
    "Information Technology", "Robotics", "Machine Learning", "Deep Learning",
    "Cloud Computing", "Internet of Things", "Cybersecurity", "Web Development",
    "DevOps", "Project Management", "Digital Marketing", "Leadership", "AWS",
    "Communication Skills",
]

GRADES = ["A", "B", "C", "D", "E", "F"]

SUSPICIOUS_SNIPPETS = [
    "Buy verified certificates online. No exam needed, instant delivery.",
    "Get your {course} certificate free, contact us on whatsapp @certseller.",
    "Unaccredited fast track certificate, pay now and receive within 24 hours.",
    "No classes required. Purchase a {course} certificate by clicking here.",
    "Certificates for sale, verified by nobody. Call 1-900-CERT-FAKE.",
    "",
    " ",
]

# Corporate / non-academic issuers. The "plain" ones contain no academic
# keyword so runtime extraction can legitimately fail to detect them, which
# mirrors real-world documents like corporate training certificates.
CORPORATE_ISSUERS = [
    "CogniTech Solutions", "BlueBridge Learning", "CloudForge", "NovaSkills",
    "Lumina Professional", "SkillPath", "Vertex Consulting Group",
    "DataDriven Institute", "Peak Performance Academy", "TechEdge Training",
    "Innovate Academy", "QuantumWorks Training", "StellarEdge Academy",
    "Meridian Skills Institute",
]
ONLINE_PLATFORMS = [
    "SkillBridge Online", "EduStream", "LearnSphere", "OpenCampus Digital",
    "CourseHub", "BrightPath Online", "NovaLearn", "StudySphere Academy",
]

# Technical certification vendors. All names are in KNOWN_NON_ACADEMIC_ISSUERS
# so genuine technical certificates produce issuer_known=1 / trust=1.0 at both
# training time and runtime.
TECHNICAL_ISSUERS = [
    "SecurEdge Labs", "CloudForge Academy", "CloudForge", "CyberShield Institute",
    "NimbusCloud Academy", "DataPulse Labs", "SecureTech Institute",
    "DevStack Training", "AIForge Labs", "NetWave Academy", "CodeCraft Institute",
    "TechEdge Training", "CogniTech Solutions", "NovaSkills",
]

ACADEMIC_TITLES = [
    "Certificate of Achievement", "Academic Certificate", "Certificate of Merit",
    "Degree Certificate", "Certificate of Academic Excellence",
]
COMPLETION_TITLES = [
    "Certificate of Completion", "Completion Certificate",
    "Course Completion Certificate",
]
TRAINING_TITLES = [
    "Professional Training Certificate", "Training Certificate",
    "Certificate of Training", "Professional Development Certificate",
]
ONLINE_TITLES = [
    "Course Certificate", "Certificate of Completion", "Online Course Certificate",
]
TECHNICAL_TITLES = [
    "Technical Certification", "Certification of Competency",
    "Professional Certification", "Developer Certification",
    "Cloud Certification", "Cybersecurity Certification",
    "IT Certification", "Data Science Certification",
    "Engineering Certification", "Software Certification",
]

# Workshop / attendance certificate titles (Phase 6B). These certify presence
# at an event, not skill acquisition, so they are distinct from training.
WORKSHOP_TITLES = [
    "Workshop Certificate", "Certificate of Attendance",
    "Seminar Participation Certificate", "Attendance Certificate",
    "Certificate of Participation",
]

# Workshop / seminar organizers. All are drawn from the known non-academic
# issuers so genuine workshop certificates produce issuer_known=1.
WORKSHOP_ISSUERS = [
    "NovaSkills", "Lumina Professional", "TechEdge Training",
    "CogniTech Solutions", "Peak Performance Academy", "Innovate Academy",
    "QuantumWorks Training", "StellarEdge Academy", "Meridian Skills Institute",
    "EduStream", "LearnSphere",
]

# Technical subject domains used by technical-certificate rows. These are a
# subset of the broader COURSES list plus a few extra vendor-style topics so
# the technical stratum is structurally different from the completion/training
# strata (which reuse COURSES).
TECHNICAL_COURSES = [
    "Cloud Computing", "Cybersecurity", "AWS", "DevOps",
    "Machine Learning", "Deep Learning", "Data Science",
    "Artificial Intelligence", "Web Development", "Information Technology",
    "Robotics", "Internet of Things", "Network Security",
    "Software Engineering", "Data Engineering",
]

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]

SUSPICIOUS_ISSUERS = [
    "Online Degree Emporium", "Diploma Fast Co.", "Instant Cert Ltd",
    "Quick Diplomas", "Grade 4 Sale", "",
]


def _valid_checksum_id(rng, year):
    base5 = "".join(str(rng.randint(0, 9)) for _ in range(5))
    return f"CERT-{year}-{base5}{cp.checksum_digit(base5)}"


def _random_person(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _random_issue_date(rng, current_year):
    year = rng.randint(cp.MIN_ISSUE_YEAR, current_year)
    return datetime(year, rng.randint(1, 12), rng.randint(1, 28)).date()


def _human_date(rng, d):
    """Render a date in one of several human-readable formats."""
    fmt = rng.choice(["iso", "month_day_year", "day_month_year", "dmy_slash"])
    if fmt == "iso":
        return d.isoformat()
    if fmt == "month_day_year":
        return f"{MONTH_NAMES[d.month - 1]} {d.day}, {d.year}"
    if fmt == "day_month_year":
        return f"{d.day} {MONTH_NAMES[d.month - 1]} {d.year}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


# --------------------------------------------------------------------------
# Genuine rows
# --------------------------------------------------------------------------

def _academic_row(rng, current_year):
    issuer = rng.choice(cp.KNOWN_ISSUERS)
    name = _random_person(rng)
    course = rng.choice(COURSES)
    year = rng.randint(cp.MIN_ISSUE_YEAR, current_year)
    issue_date = datetime(year, rng.randint(1, 12), rng.randint(1, 28)).date()
    marks_total = rng.choice([100, 100, 100, 50, 200])
    pct = rng.uniform(55, 99)
    marks_obtained = round(marks_total * pct / 100, 1)
    grade = cp.grade_band(pct)
    title = rng.choice(ACADEMIC_TITLES)
    cert_id = _valid_checksum_id(rng, year)
    return {
        "cert_id": cert_id,
        "issuer": issuer,
        "issue_date": issue_date.isoformat(),
        "candidate_name": name,
        "course": course,
        "organization": issuer,
        "marks_total": marks_total,
        "marks_obtained": marks_obtained,
        "grade": grade,
        "has_signature": rng.random() > 0.05,
        "has_seal": rng.random() > 0.10,
        "has_qr": rng.random() > 0.15,
        "has_url": False,
        "title": title,
        "certificate_type": "academic",
        "text_snippet": (
            f"{title}\n"
            f"This is to certify that {name} has successfully completed the "
            f"{course} program offered by {issuer} and was awarded the grade {grade}.\n"
            f"Certificate ID: {cert_id}\n"
            f"Marks: {marks_obtained} out of {marks_total}\n"
            f"Date of Issue: {_human_date(rng, issue_date)}\n"
            "Signature: Registrar\nSeal: Official University Seal\nQR code embedded"
        ),
        "blank_ratio": round(rng.uniform(0.02, 0.10), 4),
        "sharpness": round(rng.uniform(0.70, 0.95), 4),
        "noise_level": round(rng.uniform(0.02, 0.10), 4),
        "color_anomaly": 1 if rng.random() < 0.05 else 0,
        "label": 0,
    }


def _non_academic_row(rng, current_year, cert_type):
    """Genuine completion/training/online certificate row.

    Two issuer representations are produced so the structured columns match
    runtime extraction semantics:
      - marker style: issuer appears after "offered by"/"presented by" in the
        text and in the issuer/organization columns (detectable at runtime).
      - title-only style: the provider name appears only as a title line with
        no marker or academic keyword (not detectable at runtime) and the
        issuer/organization columns are empty, mirroring real-world docs.
    """
    name = _random_person(rng)
    course = rng.choice(COURSES)
    issue_date = _random_issue_date(rng, current_year)
    date_str = _human_date(rng, issue_date)
    marker_style = rng.random() < 0.5

    if cert_type == "completion":
        title = rng.choice(COMPLETION_TITLES)
        provider = rng.choice(CORPORATE_ISSUERS)
    elif cert_type == "training":
        title = rng.choice(TRAINING_TITLES)
        provider = rng.choice(CORPORATE_ISSUERS + cp.KNOWN_ISSUERS)
    else:  # online
        title = rng.choice(ONLINE_TITLES)
        provider = rng.choice(ONLINE_PLATFORMS + CORPORATE_ISSUERS)

    if marker_style:
        snippet = (
            f"{provider}\n{title}\n"
            f"Presented to {name} for successfully completing the {course} "
            f"program offered by {provider}.\n"
            f"Date of {cert_type}: {date_str}\n"
            "Instructor: Verified\n"
        )
        issuer_col = provider
        org_col = provider
    else:
        snippet = (
            f"{provider}\n{title}\n"
            f"Awarded to {name} upon completion of the {course} program.\n"
            f"Date of {cert_type}: {date_str}\n"
            "Instructor: Verified\n"
        )
        issuer_col = ""
        org_col = ""

    code = rng.choice(["CMP", "TRN", "ONL"])
    id_code = f"{code}-{issue_date.year}-{rng.randint(10000, 99999)}"

    return {
        "cert_id": id_code,
        "issuer": issuer_col,
        "issue_date": issue_date.isoformat(),
        "candidate_name": name,
        "course": course,
        "organization": org_col,
        "marks_total": "",
        "marks_obtained": "",
        "grade": "",
        "has_signature": rng.random() < 0.30,
        "has_seal": False,
        "has_qr": rng.random() < 0.20,
        "has_url": False,
        "title": title,
        "certificate_type": cert_type,
        "text_snippet": snippet,
        "blank_ratio": round(rng.uniform(0.02, 0.12), 4),
        "sharpness": round(rng.uniform(0.70, 0.95), 4),
        "noise_level": round(rng.uniform(0.02, 0.12), 4),
        "color_anomaly": 1 if rng.random() < 0.05 else 0,
        "label": 0,
    }


def _technical_row(rng, current_year):
    """Genuine technical-certification certificate row (Phase 5C).

    Uses TECH-YYYY-NNNN certification codes, "certified by" / "demonstrated
    proficiency" / "competency" phrasing and technical subject domains. The
    text is structurally different from the frozen external-validation
    technical PDFs (different vendoring/phrasing/date handling) and produces
    certificate_type_technical=1 at feature time.
    """
    name = _random_person(rng)
    provider = rng.choice(TECHNICAL_ISSUERS)
    course = rng.choice(TECHNICAL_COURSES)
    title = rng.choice(TECHNICAL_TITLES)
    issue_date = _random_issue_date(rng, current_year)
    date_str = _human_date(rng, issue_date)
    code = f"TECH-{issue_date.year}-{rng.randint(1000, 9999)}"
    snippet = (
        f"{provider}\n{title}\n"
        f"This is to certify that {name} has demonstrated proficiency in {course} "
        f"and is certified by {provider}.\n"
        f"Certification code : {code}\n"
        f"Date of Certification : {date_str}\n"
        "Verification code embedded\n"
        f"Instructor: {name}"
    )
    return {
        "cert_id": code,
        "issuer": provider,
        "issue_date": issue_date.isoformat(),
        "candidate_name": name,
        "course": course,
        "organization": provider,
        "marks_total": "",
        "marks_obtained": "",
        "grade": "",
        "has_signature": rng.random() < 0.20,
        "has_seal": False,
        "has_qr": rng.random() < 0.20,
        "has_url": False,
        "title": title,
        "certificate_type": "technical",
        "text_snippet": snippet,
        "blank_ratio": round(rng.uniform(0.02, 0.12), 4),
        "sharpness": round(rng.uniform(0.70, 0.95), 4),
        "noise_level": round(rng.uniform(0.02, 0.12), 4),
        "color_anomaly": 1 if rng.random() < 0.05 else 0,
        "label": 0,
    }


def _workshop_row(rng, current_year):
    """Genuine workshop / attendance certificate row (Phase 6B).

    Low-stakes attendance semantics: "We thank ... for active participation",
    "organized by" issuer marker, Workshop/Attendance/Seminar titles, no marks
    or grade. Produces certificate_type_workshop=1 (and training=1) at feature
    time while remaining structurally distinct from training certificates.
    """
    name = _random_person(rng)
    organizer = rng.choice(WORKSHOP_ISSUERS)
    course = rng.choice(COURSES)
    title = rng.choice(WORKSHOP_TITLES)
    issue_date = _random_issue_date(rng, current_year)
    date_str = _human_date(rng, issue_date)
    venue = rng.choice(["City Convention Centre", "Grand Plaza Hotel",
                        "Tech Hub Auditorium", "Community Hall"])
    code = f"WSH-{issue_date.year}-{rng.randint(10000, 99999)}"
    snippet = (
        f"{organizer}\n{title}\n"
        f"We thank {name}\nfor active participation in the {course} "
        f"workshop conducted on {date_str} at {venue}.\n"
        f"Organized by : {organizer}\n"
        "Coordinator: Workshop Committee"
    )
    return {
        "cert_id": code,
        "issuer": organizer,
        "issue_date": issue_date.isoformat(),
        "candidate_name": name,
        "course": course,
        "organization": organizer,
        "marks_total": "",
        "marks_obtained": "",
        "grade": "",
        "has_signature": rng.random() < 0.30,
        "has_seal": False,
        "has_qr": rng.random() < 0.10,
        "has_url": False,
        "title": title,
        "certificate_type": "workshop",
        "text_snippet": snippet,
        "blank_ratio": round(rng.uniform(0.02, 0.12), 4),
        "sharpness": round(rng.uniform(0.70, 0.95), 4),
        "noise_level": round(rng.uniform(0.02, 0.12), 4),
        "color_anomaly": 1 if rng.random() < 0.05 else 0,
        "label": 0,
    }


# --------------------------------------------------------------------------
# Fraud rows
# --------------------------------------------------------------------------

def _apply_fraud(rng, row, current_year):
    row["label"] = 1
    modes = [
        "future_date",
        "suspicious_text",
        "unknown_issuer",
        "blank",
        "url_present",
        "poor_visual",
    ]
    if row["certificate_type"] == "academic":
        modes += ["bad_id_format", "bad_checksum", "marks_inconsistent",
                  "grade_inconsistent", "missing_signature", "missing_seal",
                  "missing_qr", "old_date"]
    if row["certificate_type"] == "technical":
        modes += ["invalid_certification_code", "altered_name",
                  "no_technical_context"]
    if row["certificate_type"] == "workshop":
        modes += ["invalid_workshop_code", "no_event_context"]
    n_violations = rng.randint(1, 3)
    for mode in rng.sample(modes, n_violations):
        if mode == "bad_id_format":
            year = rng.randint(1990, current_year)
            row["cert_id"] = rng.choice([
                f"FREECERT-{year}-{rng.randint(100000, 999999)}",
                f"certificate-{rng.randint(10000, 99999)}",
                "No ID number",
                f"ABC-{year}-{''.join(str(rng.randint(0, 9)) for _ in range(5))}",
            ])
        elif mode == "bad_checksum":
            base5 = "".join(str(rng.randint(0, 9)) for _ in range(5))
            year = rng.randint(1990, current_year)
            check = (cp.checksum_digit(base5) + rng.randint(1, 9)) % 10
            row["cert_id"] = f"CERT-{year}-{base5}{check}"
        elif mode == "unknown_issuer":
            row["issuer"] = rng.choice(SUSPICIOUS_ISSUERS)
            row["organization"] = row["issuer"]
            row["text_snippet"] = (
                f"{row['title']}\n"
                f"Presented to {row['candidate_name']} for the {row['course']} program."
            )
        elif mode == "future_date":
            future = datetime(current_year + 1, rng.randint(1, 12),
                              rng.randint(1, 28))
            row["issue_date"] = future.date().isoformat()
        elif mode == "old_date":
            row["issue_date"] = f"19{rng.randint(50, 89)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        elif mode == "marks_inconsistent":
            row["marks_obtained"] = int(row["marks_total"]) + rng.randint(1, 60)
        elif mode == "grade_inconsistent":
            pct = rng.uniform(0, 100)
            row["grade"] = cp.grade_band(pct)
            row["marks_obtained"] = round(float(row["marks_total"]) * rng.uniform(95, 99) / 100, 1)
        elif mode == "suspicious_text":
            row["text_snippet"] = rng.choice(SUSPICIOUS_SNIPPETS).format(
                course=row["course"])
        elif mode == "missing_signature":
            row["has_signature"] = False
        elif mode == "missing_seal":
            row["has_seal"] = False
        elif mode == "missing_qr":
            row["has_qr"] = False
        elif mode == "invalid_certification_code":
            row["cert_id"] = rng.choice([
                "TEC-2024-12", "CERT-2024-99999", "No code",
                f"TECH-{rng.randint(1990, current_year)}-",
                "ABCD",
            ])
        elif mode == "altered_name":
            row["candidate_name"] = rng.choice([
                "Buy Certificates", "Instant Certificates", "Pay Now Cert",
            ])
            row["text_snippet"] = (row["text_snippet"] +
                                   "\nName altered on this certificate.")
        elif mode == "no_technical_context":
            # Generic completion phrasing with no certification/proficiency
            # context: the document loses its technical-type flag, mirroring a
            # fraudster producing a generic-looking "technical" document.
            row["text_snippet"] = (
                f"{row['title']}\n"
                f"Presented to {row['candidate_name']} for attending the "
                f"{row['course']} course offered by {row['organization']}.\n"
                f"Date of issue: {row['issue_date']}"
            )
            row["title"] = "Course Certificate"
        elif mode == "invalid_workshop_code":
            row["cert_id"] = rng.choice([
                "WSH-2024-", "No code", "ATT-1234", "ABC123",
            ])
        elif mode == "no_event_context":
            # Missing attendance/participation wording: generic certificate
            # with no event context, so the workshop flag does not fire.
            row["text_snippet"] = (
                f"{row['title']}\n"
                f"This is to certify that {row['candidate_name']} completed the "
                f"{row['course']} course offered by {row['organization']}.\n"
                f"Date of issue: {row['issue_date']}"
            )
            row["title"] = "Certificate of Completion"
        elif mode == "blank":
            row["text_snippet"] = " "
            # Runtime compute_visual measures the fraction of dark/ink pixels,
            # so a blank page scores ~0. Training must use the same low range
            # so the visual_blank_ratio feature means the same thing at
            # training time and runtime.
            row["blank_ratio"] = round(rng.uniform(0.0, 0.05), 4)
            row["candidate_name"] = ""
            row["course"] = ""
            row["issuer"] = ""
            row["organization"] = ""
        elif mode == "poor_visual":
            row["sharpness"] = round(rng.uniform(0.10, 0.40), 4)
            row["noise_level"] = round(rng.uniform(0.25, 0.60), 4)
            row["color_anomaly"] = rng.randint(0, 1)
        elif mode == "url_present":
            row["has_url"] = True
            row["text_snippet"] = (row["text_snippet"] +
                                   " Contact us at www.instantcerts.com")
    return row


# --------------------------------------------------------------------------
# Dataset assembly
# --------------------------------------------------------------------------

def _genuine_for_type(rng, current_year, cert_type):
    if cert_type == "academic":
        return _academic_row(rng, current_year)
    if cert_type == "technical":
        return _technical_row(rng, current_year)
    if cert_type == "workshop":
        return _workshop_row(rng, current_year)
    return _non_academic_row(rng, current_year, cert_type)


def generate_dataset(size: int, fraud_ratio: float, seed: int) -> list:
    rng = random.Random(seed)
    current_year = datetime.now(timezone.utc).year
    types = ["academic", "completion", "training", "online", "technical", "workshop"]

    rows = []
    per_type = max(size // len(types), 1)
    for cert_type in types:
        n_fraud = round(per_type * fraud_ratio)
        for _ in range(per_type):
            row = _genuine_for_type(rng, current_year, cert_type)
            if len(rows) % per_type < n_fraud:
                row = _apply_fraud(rng, row, current_year)
            rows.append(row)

    # 5% label noise so the problem is not trivially separable.
    for row in rows:
        if rng.random() < 0.05:
            row["label"] = 1 - row["label"]
    return rows


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic certificate dataset")
    parser.add_argument("--output", default=os.environ.get("DATA_RAW_DIR", "./data/raw/certificates.csv"))
    parser.add_argument("--size", type=int, default=4000)
    parser.add_argument("--fraud-ratio", type=float, default=0.30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import pandas as pd

    rows = generate_dataset(args.size, args.fraud_ratio, args.seed)
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    df.to_csv(args.output, index=False)
    counts = df["certificate_type"].value_counts().to_dict()
    print(f"Wrote {len(df)} rows ({df['label'].sum()} positive) to {args.output}")
    print(f"By type: {counts}")


if __name__ == "__main__":
    main()