"""Shared certificate patterns and heuristics used by data generation,
feature engineering, and runtime extraction so everything stays consistent.

All data in this project is synthetic; these patterns model *plausible*
certificate structures for a prototype fraud-risk classifier.
"""

import re

CERT_ID_REGEX = re.compile(r"^CERT-(\d{4})-(\d{6})$")

KNOWN_ISSUERS = [
    "University of Cambridge",
    "University of Oxford",
    "Stanford University",
    "Massachusetts Institute of Technology",
    "Harvard University",
    "ETH Zurich",
    "University of Toronto",
    "University of Melbourne",
    "National University of Singapore",
    "TU Munich",
    "Indian Institute of Technology Delhi",
    "IIT Bombay",
    "Anna University",
    "Delhi University",
    "University of Washington",
    "KAIST",
    "Imperial College London",
]

# Legitimate non-academic issuers (corporate trainers, online platforms,
# technical vendors) used by completion/training/online/technical/workshop
# certificates. These are legitimate organizations, not suspicious issuers.
KNOWN_NON_ACADEMIC_ISSUERS = [
    "NovaSkills",
    "SecurEdge Labs",
    "CloudForge Academy",
    "CogniTech Solutions",
    "EduStream",
    "LearnSphere",
    "Peak Performance Academy",
    "TechEdge Training",
    "Lumina Professional",
    # Technical certification vendors. "CloudForge" is the short form that
    # runtime issuer extraction produces for "CloudForge Academy" when the
    # text wraps the vendor name across lines, so both spellings are known.
    "CloudForge",
    "CyberShield Institute",
    "NimbusCloud Academy",
    "DataPulse Labs",
    "SecureTech Institute",
    "DevStack Training",
    "AIForge Labs",
    "NetWave Academy",
    "CodeCraft Institute",
    # Legitimate workshop / seminar organizers (Phase 6B). These are drawn
    # from the v4 workshop stratum so genuine workshop/attendance certificates
    # produce issuer_known=1 / trust=1.0 at both training time and runtime.
    "Innovate Academy",
    "QuantumWorks Training",
    "StellarEdge Academy",
    "Meridian Skills Institute",
]

SUSPICIOUS_KEYWORDS = [
    "buy",
    "purchase",
    "no exam",
    "instant",
    "get certificate",
    "verified certificate",
    "free certificate",
    "fast track",
    "unaccredited",
    "whatsapp",
    "pay now",
    "click here",
]

URL_MARKERS = ["www.", "http://", "https://", ".com", "@mail", "contact us"]

MIN_ISSUE_YEAR = 1990

# Certificate title markers. A "completion_title_present" document contains
# one of these in its title line.
CERT_TITLE_KEYWORDS = [
    "certificate",
    "certification",
    "diploma",
    "credential",
    "certificate of achievement",
    "certificate of completion",
    "certificate of training",
]

# Certificate-type detection keywords. These are intentionally broad so the
# runtime extractor and the training pipeline share one semantic.
ACADEMIC_KEYWORDS = [
    "university", "college", "polytechnic", "degree", "academic",
    "baccalaureate", "bachelor", "doctorate", "graduation", "graduated",
    "faculty of", "semester", "thesis", "dissertation", "merit",
]

# Academic content evidence (marks/grades) that distinguishes a university
# certificate from a vendor/training certificate.
ACADEMIC_CONTEXT_KEYWORDS = ["marks", "grade", "cgpa", "gpa"]
COMPLETION_KEYWORDS = ["completion"]
TRAINING_KEYWORDS = ["training", "professional", "development", "workshop", "course"]

# Technical certificate detection (Phase 5C).
#
# A document is classified "technical" only when BOTH signals are present:
#   - TECHNICAL_CONTEXT_KEYWORDS: phrasing/verbiage indicating a formal
#     certification of competence (e.g. "Technical Certification", "certified
#     by", "demonstrated proficiency", "certification code").
#   - TECHNICAL_DOMAIN_KEYWORDS: a technical subject domain (cloud, security,
#     AWS, data science, machine learning, engineering, ...).
#
# Context is the gate so that a plain completion/training/online/workshop
# certificate for a technical course (e.g. "Certificate of Completion ... Cloud
# Computing program") is NOT classified technical, and mentioning the word
# "technology" alone does not classify a document technical. Academic documents
# are excluded outright (university/degree/marks/grade), so a university degree
# mentioning "engineering" is never flagged technical.
TECHNICAL_CONTEXT_KEYWORDS = [
    "certification",
    "certified by",
    "certification code",
    "technical certification",
    "technology certification",
    "professional certification",
    "developer certification",
    "cloud certification",
    "cybersecurity certification",
    "software certification",
    "engineering certification",
    "it certification",
    "data science certification",
    "machine learning certification",
    "programming certification",
    "technical course",
    "demonstrated proficiency",
    "proficiency in",
    "competency",
]

TECHNICAL_DOMAIN_KEYWORDS = [
    "cloud", "cybersecurity", "security", "network", "networking",
    "software", "developer", "programming", "coding", "devops", "aws",
    "web development", "data science", "machine learning", "deep learning",
    "artificial intelligence", "information technology",
    "kubernetes", "docker", "python", "java", "javascript", "sql",
    "engineering", "robotics", "internet of things", "data analytics",
    "big data",
]

# Workshop / attendance certificate detection (Phase 6A). A document is
# classified "workshop" when it signals attendance/participation/seminar
# wording (e.g. "Seminar Participation Certificate", "attended the workshop").
# These are the lowest-stakes certificates: they certify presence at an event,
# not the acquisition of a skill, so the fraud-risk profile differs from
# training/completion certificates. The flag is independent of the other type
# flags (a university seminar attendance certificate is legitimately both
# academic and workshop). "workshop"/"seminar"/"course" also still fire the
# training flag, mirroring v2 behaviour.
WORKSHOP_KEYWORDS = [
    "workshop", "seminar", "attendance", "attended", "participation",
    "participated", "participant",
]

# Issuer markers that indicate an issuer/organization name even when the
# issuer has no academic keyword (e.g. corporate providers).
ISSUER_MARKERS = [
    "issued by", "presented by", "awarded by", "provided by",
    "conducted by", "training provider", "instructor", "offered by",
]

# Recipient phrases. Mirrors the runtime extraction recipient regex.
RECIPIENT_PHRASES = [
    "certify that", "certifies that", "awarded to", "presented to",
    "completed by", "this certificate is awarded to",
]


def _technical_detected(low: str) -> bool:
    """True if a document carries genuine technical-certification signals.

    Requires technical context phrasing AND a technical subject domain AND no
    strong academic markers. Word-boundary matching is used for the domain so
    short keywords such as "aws" do not match inside unrelated words.
    """
    if any(k in low for k in ACADEMIC_KEYWORDS) or any(
        k in low for k in ACADEMIC_CONTEXT_KEYWORDS
    ):
        return False
    if not any(k in low for k in TECHNICAL_CONTEXT_KEYWORDS):
        return False
    return any(re.search(rf"\b{re.escape(kw)}\b", low) for kw in TECHNICAL_DOMAIN_KEYWORDS)


def certificate_type_flags(text: str, issuer: str = "") -> dict:
    """Return independent academic/completion/training/technical flags.

    Flags are intentionally independent (a university training certificate
    can legitimately be both academic and training). Academic detection
    requires strong academic markers (university/college/degree/academic) or
    academic content (marks/grades); vendor names such as "CloudForge Academy"
    or "Peak Performance Academy" do not by themselves mark a document
    academic. Technical detection additionally requires certification-style
    context + a technical subject domain and is suppressed for academic
    documents. Used identically by the training pipeline and runtime feature
    service.
    """
    low = (text or "").lower()
    iss = (issuer or "").lower()
    academic = any(k in low or k in iss for k in ACADEMIC_KEYWORDS) or any(
        k in low for k in ACADEMIC_CONTEXT_KEYWORDS
    )
    return {
        "academic": int(academic),
        "completion": int(any(k in low or k in iss for k in COMPLETION_KEYWORDS)),
        "training": int(any(k in low or k in iss for k in TRAINING_KEYWORDS)),
        "technical": int(_technical_detected(low)),
        "workshop": int(any(k in low or k in iss for k in WORKSHOP_KEYWORDS)),
    }


def certificate_title_present(text: str) -> bool:
    """True if the document mentions a certificate title keyword."""
    if not text:
        return False
    low = text.lower()
    return any(k in low for k in CERT_TITLE_KEYWORDS)


def recipient_present(text: str) -> bool:
    """True if a recipient phrase is present in the document text."""
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in RECIPIENT_PHRASES)


def checksum_digit(digits: str) -> int:
    """Simple checksum used for synthetic certificate ids.

    Sums digit * (position + 1) and returns (sum % 10).
    """
    if not digits or not digits.isdigit():
        return -1
    total = sum(int(d) * (i + 1) for i, d in enumerate(digits))
    return total % 10


def cert_id_checksum_valid(cert_id: str) -> bool:
    match = CERT_ID_REGEX.match(cert_id or "")
    if not match:
        return False
    base5 = match.group(2)[:5]
    return checksum_digit(base5) == int(match.group(2)[5])


def cert_id_format_valid(cert_id: str) -> bool:
    return bool(CERT_ID_REGEX.match(cert_id or ""))


def issuer_known(issuer: str) -> bool:
    return bool(issuer) and issuer.strip().lower() in {
        i.lower() for i in KNOWN_ISSUERS + KNOWN_NON_ACADEMIC_ISSUERS
    }


def issue_year_valid(year) -> bool:
    try:
        return MIN_ISSUE_YEAR <= int(year) <= 2026
    except (TypeError, ValueError):
        return False


def grade_band(pct: float) -> str:
    if pct >= 90:
        return "A"
    if pct >= 75:
        return "B"
    if pct >= 60:
        return "C"
    if pct >= 50:
        return "D"
    if pct >= 35:
        return "E"
    return "F"


def grade_consistent(grade: str, pct: float) -> bool:
    return bool(grade) and grade.strip().upper() == grade_band(pct)


def suspicious_keyword_count(text: str) -> int:
    if not text:
        return 0
    low = text.lower()
    return sum(1 for kw in SUSPICIOUS_KEYWORDS if kw in low)


def suspicious_url_present(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in URL_MARKERS)
