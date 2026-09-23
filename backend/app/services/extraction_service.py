"""Document extraction service.

Extracts text, structured fields, and visual/structural signals from a
certificate PDF or image:

- PDF: embedded text via PyMuPDF; visual features from the first page render.
  When the embedded text layer is insufficient (scanned / image-heavy
  documents), pages are rendered to images and OCR is run as a fallback
  (Phase 10). The combined result is reported with extraction metadata.
- Image: visual/structural features via Pillow/numpy; OCR text via the
  centralized OCR layer.

OCR is best-effort and NEVER crashes verification: a missing engine or failed
read degrades to structural signals alone, with a clear warning. Missing
fields stay missing — they are never treated as fraud.
"""

import re
import warnings
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFilter
from scipy.signal import convolve2d

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from app.core.config import settings
from app.core.logging import get_logger
from app.services.ocr_service import ocr_image

logger = get_logger("extraction_service")

CERT_ID_RE = re.compile(r"(?<![A-Za-z0-9])CERT-\d{4}-\d{6}(?![A-Za-z0-9])")
NAME_RE = re.compile(
    r"(?i:certif(?:y|ies)[ \t]+that|awarded[ \t]+to|presented[ \t]+to|"
    r"present[ \t]+this[ \t]+certificate[ \t]+to|completed[ \t]+by|"
    r"this[ \t]+certificate[ \t]+is[ \t]+awarded[ \t]+to|we[ \t]+thank)"
    r"\s*?([A-Z][a-zA-Z.'\-]*(?:[ \t]+[A-Z][a-zA-Z.'\-]*){1,3})"
)
# Real-world certificates often put the recipient BEFORE the completion verb
# ("Rohith Kumar K R has completed practical tasks in:"). Fallback pattern used
# only when NAME_RE finds no recipient phrase.
NAME_PRE_RE = re.compile(
    r"([A-Z][a-zA-Z.'\-]*(?:[ \t]+[A-Z][a-zA-Z.'\-]*){1,3})"
    r"[ \t]+(?:has[ \t]+(?:successfully[ \t]+)?completed|"
    r"has[ \t]+completed[ \t]+practical|successfully[ \t]+completed|"
    r"completed[ \t]+the[ \t]+(?:course|program|module|task))",
    re.IGNORECASE,
)
MONTH_NAMES = (
    r"january|february|march|april|may|june|july|august|"
    r"september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec"
)
DATE_RE = re.compile(
    r"\b(?:"
    r"((?:19|20)\d{2})[-/.]((?:0?[1-9]|1[0-2]))[-/.]((?:0?[1-9]|[12]\d|3[01]))|"
    r"((?:0?[1-9]|[12]\d|3[01]))[-/.]((?:0?[1-9]|1[0-2]))[-/.]((?:19|20)\d{2})|"
    rf"({MONTH_NAMES})[.,]?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{{2}})|"
    rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_NAMES}),?\s+((?:19|20)\d{{2}})"
    r")\b",
    re.IGNORECASE,
)
_FULL_MONTHS = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
]
_MONTH_ABBREV = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MONTH_MAP = {name: i for i, name in enumerate(_FULL_MONTHS, start=1)}
MONTH_MAP.update(_MONTH_ABBREV)
MARKS_RE = re.compile(
    r"(?i:(?:marks?|score|percentage|percent|obtained|total)"
    r"(?:[ \t]+(?:obtained|scored|achieved))?[ \t]*[:.]?[ \t]*"
    r"(\d+(?:\.\d+)?)[ \t]*(?:out[ \t]+of|/|of)[ \t]*(\d+(?:\.\d+)?))"
)
GRADE_RE = re.compile(r"grade\s*[:.]?\s*([A-F])", re.IGNORECASE)
ISSUER_MARKER_RE = re.compile(
    r"(?:issued by|presented by|awarded by|provided by|conducted by|"
    r"training provider|instructor|offered by|certified by|organized by)"
    r"[ \t]*:?[ \t]*(.+)",
    re.IGNORECASE,
)
# Explicit labeled issuer fields, e.g. "Organization: Acme", "Institute: IIT".
ISSUER_FIELD_RE = re.compile(
    r"(?i:\b(?:organization|institution|university|college|institute|academy)"
    r"[ \t]*[:.][ \t]*([^\r\n]+))"
)
# Clause boundaries that can follow an issuer name in a sentence, e.g.
# "...offered by University of Cambridge and was awarded the grade A."
# Affiliation clauses ("...provided by Cisco Networking Academy in
# collaboration with OpenEDG Python Institute") commonly appear in image-heavy
# certificates; the issuing organization is the part BEFORE the clause.
ISSUER_CLAUSE_SPLIT_RE = re.compile(
    r"\s+and\s+(?=[a-z])|\s*,\s*|\s+which\b|\s+who\b|\s+upon\b|"
    r"\s+in\s+(?:collaboration|partnership|association|cooperation|"
    r"conjunction)\s+with\b"
)

# Labeled credential identifiers (verification codes, certificate IDs,
# reference numbers, ...). Real-world certificates carry these to allow
# issuer-side verification. Their presence is extracted as a signal; it is the
# verification-code analysis layer (not extraction) that decides whether the
# code can actually be verified.
VERIFICATION_CODE_LABELS = [
    "enrolment verification code", "enrollment verification code",
    "user verification code", "verification code", "verification url",
    "enrolment code", "enrollment code", "verification id",
    "verification number", "candidate code", "credential id",
    "credential code", "certificate id", "certificate no",
    "certification code", "reference number", "reference no",
    "serial number", "serial no", "certificate number",
]
_CODE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{3,63}")


def _extract_verification_codes(text: str) -> tuple[list[dict], bool]:
    """Extract labeled credential identifiers from document text.

    Returns ``(codes, present)`` where each code is
    ``{"label", "code", "kind"}``. ``kind`` is one of
    ``issuer_verification_code`` | ``certificate_id`` | ``reference_number`` |
    ``credential_identifier``. Extraction only records the identifier and its
    label; it never decides whether the code is genuine.
    """
    codes: list[dict] = []
    if not text:
        return codes, False
    low = text.lower()
    for label in VERIFICATION_CODE_LABELS:
        start = 0
        while True:
            idx = low.find(label, start)
            if idx < 0:
                break
            tail = text[idx + len(label):]
            m = re.search(r"[ \t]*[:.]?[ \t]*(" + _CODE_TOKEN_RE.pattern + r")", tail)
            if m:
                code = m.group(1)
                if not any(c["code"] == code for c in codes):
                    kind = "issuer_verification_code"
                    if any(k in label for k in ("certificate", "certification", "credential")):
                        kind = "certificate_id"
                    elif any(k in label for k in ("reference", "serial")):
                        kind = "reference_number"
                    codes.append({"label": label, "code": code, "kind": kind})
            start = idx + len(label)
    return codes, bool(codes)


def _clean_issuer_marker(value: str) -> str:
    """Trim trailing clause text and punctuation from a marker capture."""
    value = re.split(ISSUER_CLAUSE_SPLIT_RE, value, maxsplit=1)[0]
    # OCR often breaks "X in collaboration with Y" across lines, leaving a
    # dangling preposition on the issuer line ("X in"). Drop trailing
    # prepositional words so "X in" becomes "X".
    value = re.sub(r"\s+(?:in|by|with|at|for|from|the|and)\s*$", "", value)
    return value.rstrip(" .:;,()\"'")[:100]


# Values that can be captured by issuer markers but are not organization
# names (e.g. "Awarded by the course faculty").
GENERIC_ISSUER_VALUES = {
    "the course faculty", "course faculty", "the faculty", "faculty",
    "the committee", "committee", "the organizers", "organizers",
    "the management", "management", "the coordinator", "coordinator",
    "the participants", "participants", "the participant", "participant",
    "verified", "the department", "department", "the staff", "staff",
    "the organizers and coordinators",
}


def _is_generic_issuer(value: str) -> bool:
    """True if a capture looks like boilerplate rather than an organization."""
    cand = (value or "").strip()
    if not cand:
        return True
    low = cand.lower()
    if low in GENERIC_ISSUER_VALUES:
        return True
    if len(cand) < 3 or len(cand) > 60:
        return True
    if re.fullmatch(r"the[ \t]+[a-z][a-z \t]*", low):
        return True
    # A bare organizational noun ("Academy", "University", ...) is boilerplate,
    # not an issuer name — it needs a qualifier (e.g. "Cisco Networking
    # Academy"). Common when OCR splits an issuer heading across lines.
    if len(cand.split()) == 1 and low in (
        "academy", "university", "institute", "college", "school",
        "polytechnic", "academia",
    ):
        return True
    if not re.search(r"[A-Z]", cand):
        return True
    return False


# Recipient/issuer phrases that disqualify a nearby line from being a
# title-line organization heading.
_ORG_REJECT_MARKERS = (
    "certify that", "certifies that", "awarded to", "presented to",
    "present this certificate to", "completed by", "we thank",
    "this certificate is awarded to", "issued by", "certified by",
    "organized by", "awarded by", "presented by", "offered by",
    "provided by", "conducted by", "training provider", "instructor",
)


def _plausible_org_line(line: str) -> str:
    """Return a plausible short organization heading, or '' otherwise."""
    cand = (line or "").strip().rstrip(" .:;,()\"'")
    if not cand or len(cand) < 3 or len(cand) > 40:
        return ""
    if len(cand.split()) > 4:
        return ""
    low = cand.lower()
    if any(m in low for m in _ORG_REJECT_MARKERS):
        return ""
    if DATE_RE.search(cand):
        return ""
    if _is_generic_issuer(cand):
        return ""
    return cand[:100]


def _title_line_issuer(text: str) -> str:
    """Detect an issuer heading adjacent to the certificate title line."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not _is_title_line(line):
            continue
        # Reject corporate-style headings that merely end in "Certification"
        # (e.g. "AWS Training & Certification", "Director, AWS Training &
        # Certification") so a signatory's name is not mistaken for an issuer.
        if "&" in line or "," in line:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines):
                org = _plausible_org_line(lines[j])
                if org:
                    return org
    return ""


def _extract_issuer(text: str) -> str:
    """Best-effort organization extraction: labeled fields, issuer markers,
    keyword fallback, then title-line adjacency."""
    m = ISSUER_FIELD_RE.search(text)
    if m:
        org = _clean_issuer_marker(m.group(1))
        if not _is_generic_issuer(org):
            return org

    m = ISSUER_MARKER_RE.search(text)
    if m:
        org = _clean_issuer_marker(m.group(1))
        if not _is_generic_issuer(org):
            return org

    for line in text.splitlines():
        line_low = line.lower()
        # A comma usually marks a role/signatory phrase ("Director, Acme"),
        # not an organization name; the title-line adjacency below handles
        # those headings instead.
        if any(k in line_low for k in ORG_KEYWORDS) and len(line.strip()) > 4 and "," not in line:
            org = _clean_issuer_marker(line.strip())
            if not _is_generic_issuer(org):
                return org

    return _title_line_issuer(text)

COURSE_KEYWORDS = [
    "computer science", "electrical engineering", "mechanical engineering",
    "business administration", "data science", "artificial intelligence",
    "civil engineering", "biotechnology", "economics", "information technology",
    "robotics", "mba", "machine learning", "deep learning", "cloud computing",
    "internet of things", "cybersecurity", "web development", "devops",
    "project management", "digital marketing", "leadership", "aws",
    "communication skills",
    # --- Phase 5C technical course coverage ---
    "network security", "software engineering", "data engineering",
    "cloud architecture", "kubernetes",
]
ORG_KEYWORDS = ["university", "institute", "college", "academy", "school", "polytechnic"]
TITLE_KEYWORDS = [
    "certificate", "certification", "diploma", "credential",
    "certificate of achievement", "certificate of completion",
]


def _is_title_line(line: str) -> str:
    """Classify a line as a certificate title.

    Returns 'certificate', 'certification', or '' (not a title). A line that
    starts or ends with the word 'certificate' is preferred over 'certification'
    so corporate names like 'AWS Training & Certification' are not mistaken for
    a title when a real 'Completion Certificate' line exists.
    """
    low = line.strip().lower()
    if not low or len(low) > 60:
        return ""
    if low.startswith("certificate") or low.endswith("certificate"):
        return "certificate"
    if low.startswith("certification") or low.endswith("certification"):
        return "certification"
    return ""


def _certificate_like(text: str) -> bool:
    """True when the text contains an explicit certificate title line.

    Used to gate the recipient-name fallback for text-layer PDFs: a standalone
    name line is only a credible recipient when the document already declares
    itself a certificate. This keeps arbitrary title-case lines in unrelated
    documents from being misread as recipients.
    """
    if not text:
        return False
    return any(bool(_is_title_line(line)) for line in text.splitlines())


def _normalize_date_match(m: re.Match) -> str | None:
    """Normalize a DATE_RE match to ISO YYYY-MM-DD regardless of pattern."""
    if m.group(1):
        y, mo, d = m.group(1), m.group(2), m.group(3)
    elif m.group(4):
        d, mo, y = m.group(4), m.group(5), m.group(6)
    elif m.group(7):
        mo = MONTH_MAP[m.group(7).lower()]
        y, d = m.group(9), m.group(8)
    elif m.group(10):
        mo = MONTH_MAP[m.group(11).lower()]
        d, y = m.group(10), m.group(12)
    else:
        return None
    try:
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# OCR-derived fallback extraction (Phase 10)
#
# OCR text has no semantic markup, so standalone lines can carry the key
# identity fields. These helpers ONLY run on OCR-derived text (not on normal
# text-layer PDFs) to avoid regressions on existing documents.
# --------------------------------------------------------------------------

_NAME_WORD_RE = re.compile(
    r"^[A-Z][A-Za-z.'\-]*(?:[ \t]+[A-Z][A-Za-z.'\-]*){1,4}$"
)

_ORG_SUFFIX_TERMS = (" ltd", " llc", " inc", " gmbh", " pvt", " corp", " plc", " sa")


def _name_looks_organizational(name: str) -> bool:
    """True when a candidate recipient looks like an organization/boilerplate
    rather than a person's name. Guards the name-before-verb fallback so
    sentences such as 'The Training Academy has completed...' are not misread
    as a recipient."""
    low = (name or "").strip().lower()
    if not low:
        return True
    if any(k in low for k in _BARE_NAME_BLACKLIST):
        return True
    if any(t in low for t in _ORG_SUFFIX_TERMS):
        return True
    if low.startswith(("the ", "a ", "an ")):
        return True
    if any(k in low for k in COURSE_KEYWORDS):
        return True
    return False

# Words/phrases that identify a line as an organization, role, or boilerplate
# rather than a person's name.
_BARE_NAME_BLACKLIST = (
    "academy", "university", "college", "institute", "school", "polytechnic",
    "training", "certification", "certificate", "accreditation", "authority",
    "corporation", "incorporated", "inc", "ltd", "llc", "company", "limited",
    "services", "solutions", "technologies", "empire", "emporium", "platform",
    "network", "director", "manager", "president", "chairman", "founder",
    "professor", "dr.", "sir", "participant", "department", "faculty",
    "committee", "organizer", "coordinator", "instruction", "curriculum",
    "registry", "office", "department of", "grade", "signature", "seal",
)

_LABELED_LINE_RE = re.compile(
    r"^\s*(?:course|program|title|topic|subject|cert[ \t]+id|certificate[ \t]+id"
    r"|candidate[ \t]+id|roll[ \t]+no|issu(?:ed|ance)[ \t]+date|date[ \t]+of|"
    r"completion[ \t]+date|grade|marks|score|credits?|duration|hours)[ \t]*[:.]",
    re.IGNORECASE,
)


def _extract_bare_name(text: str) -> str | None:
    """Find a standalone all-caps / title-case name line in OCR text.

    OCR text loses recipient phrases ('Awarded to ...'), so a name may sit on
    its own line. Prefer fully-uppercase lines (typical of prominent name
    typography), then the first plausible title-case line.
    """
    best: str | None = None
    for line in text.splitlines():
        cand = line.strip().strip(".,;:()\"'")
        if not cand or len(cand) < 5 or len(cand) > 60:
            continue
        if re.search(r"\d", cand):
            continue
        if not _NAME_WORD_RE.match(cand):
            continue
        low = cand.lower()
        if any(k in low for k in _BARE_NAME_BLACKLIST):
            continue
        if any(k in low for k in COURSE_KEYWORDS):
            continue
        if _is_title_line(cand):
            continue
        if _plausible_org_line(cand):
            continue  # looks like an organization heading
        all_caps = cand == cand.upper() and len([c for c in cand if c.isalpha()]) >= 4
        if all_caps:
            return cand
        if best is None:
            best = cand
    return best


def _extract_course_fallback(text: str, fields: dict) -> str | None:
    """Find a course-title line in OCR text when no keyword matched.

    Takes the longest non-boilerplate line that is not the issuer, the
    recipient, a title, a date, or a labeled metadata line.
    """
    issuer = (fields.get("organization") or "").strip().lower()
    name = (fields.get("candidate_name") or "").strip().lower()
    best: str | None = None
    for line in text.splitlines():
        cand = line.strip().strip(".,;:()\"'\"")
        if not cand or len(cand) < 3 or len(cand) > 120:
            continue
        low = cand.lower()
        if issuer and low == issuer:
            continue
        if name and low == name:
            continue
        if _is_title_line(cand):
            continue
        if _LABELED_LINE_RE.match(line):
            continue
        if DATE_RE.search(cand):
            continue
        if _plausible_org_line(cand) and not any(k in low for k in COURSE_KEYWORDS):
            # Organization-looking headings are the issuer or boilerplate.
            if issuer and low != issuer:
                continue
        if best is None or len(cand) > len(best):
            best = cand
    return best[:100] if best else None


@dataclass
class ExtractionResult:
    text: str = ""
    page_count: int = 1
    visual: dict = field(default_factory=dict)
    fields: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    ocr_used: bool = False
    # --- Phase 10 extraction metadata ---
    extraction_method: str = "none"          # pdf_text | ocr | hybrid | none
    extraction_confidence: float | None = None  # 0..1
    extracted_text_length: int = 0
    extraction_completeness: float = 0.0     # fraction of 5 core fields
    ocr_failed: bool = False
    ocr_pages: int = 0


# --------------------------------------------------------------------------
# Extraction quality helpers (Phase 10)
# --------------------------------------------------------------------------

CORE_IDENTITY_FIELDS = ("candidate_name", "organization", "course", "issue_date", "cert_id")


def _core_completeness(fields: dict) -> float:
    """Fraction of the 5 core identity fields present (0..1)."""
    present = sum(1 for k in CORE_IDENTITY_FIELDS if fields.get(k) and str(fields.get(k)).strip())
    return round(present / len(CORE_IDENTITY_FIELDS), 4)


def _text_sufficient(text: str, fields: dict) -> bool:
    """Decide whether the embedded text layer is good enough to trust.

    A PDF may carry a small text layer (e.g. accessibility text) while the
    visible content is a rendered image. In that case OCR is needed. We
    trigger OCR when:

      - there is no embedded text at all, or
      - the embedded text is shorter than ``ocr_min_text_chars``, or
      - the embedded text is short AND few core fields were detected
        (image-heavy certificate with a partial text layer).

    Returns True only when the text layer looks sufficient.
    """
    t = (text or "").strip()
    if not t:
        return False
    chars = len(t)
    if chars < settings.ocr_min_text_chars:
        return False
    completeness = _core_completeness(fields)
    if completeness >= settings.ocr_min_completeness:
        return True
    # Short text + no core fields: likely an image-heavy certificate.
    if chars < settings.ocr_hybrid_chars:
        return False
    return True


# --------------------------------------------------------------------------
# Visual / structural features
# --------------------------------------------------------------------------

def compute_visual(img: Image.Image) -> dict:
    img = img.convert("RGB")
    img.thumbnail((1200, 1200))

    gray = np.asarray(img.convert("L"), dtype=np.float32)
    if gray.size == 0:
        return {
            "visual_blank_ratio": 0.0,
            "visual_sharpness": 0.0,
            "visual_noise": 0.0,
            "visual_color_anomaly": 0,
        }

    # "blank_ratio" = fraction of dark (ink) pixels. This keeps runtime
    # extraction aligned with the training feature distribution, where
    # genuine documents have low values (0.02-0.10) and heavily filled /
    # tampered pages have high values. A normal certificate page is mostly
    # white, so the fraction of DARK pixels is the consistent measure.
    ink_ratio = float(np.mean(gray < 60))
    blank_ratio = round(min(max(ink_ratio, 0.0), 1.0), 4)

    lap = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    lap_img = convolve2d(gray, lap, mode="same", boundary="symm")
    sharpness = float(np.clip(np.var(lap_img) / 400.0, 0.0, 1.0))

    blurred = np.asarray(
        img.convert("L").filter(ImageFilter.MedianFilter(3)), dtype=np.float32
    )
    noise = float(np.clip(np.mean(np.abs(gray - blurred)) / 30.0, 0.0, 1.0))

    hsv = np.asarray(img.convert("HSV"), dtype=np.float32)
    saturation = float(np.mean(hsv[:, :, 1]) / 255.0)
    color_anomaly = 1 if saturation > 0.35 else 0

    return {
        "visual_blank_ratio": blank_ratio,
        "visual_sharpness": round(sharpness, 4),
        "visual_noise": round(noise, 4),
        "visual_color_anomaly": color_anomaly,
    }


def _first_page_image(pdf: fitz.Document) -> Image.Image:
    page = pdf[0]
    pix = page.get_pixmap(dpi=150)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


# --------------------------------------------------------------------------
# Field extraction
# --------------------------------------------------------------------------

# Generic course-title patterns (run on ALL text, unlike the OCR-only
# fallback). Certificates phrase their course in many ways that the fixed
# keyword list cannot cover (e.g. "CCNA: Introduction to Networks").
_COURSE_LABEL_RE = re.compile(
    r"\b(?:course(?:\s+title)?|programme?|subject|module|track|pathway|"
    r"area\s+of\s+study|specialization|specialisation|certification\s+name)"
    r"\s*[:.\-]\s*([^\n]{3,120})",
    re.IGNORECASE,
)
_COURSE_PHRASE_RE = re.compile(
    r"\b(?:for\s+successfully\s+completing|for\s+completing|completing\s+the|"
    r"completing|completed\s+the|completed|completion\s+of|"
    r"for\s+successful\s+completion\s+of)[:.]?[ \t]*\n?[ \t]*"
    r"((?-i:[A-Z])[A-Za-z0-9'’ /&+:.\-]{2,120})",
    re.IGNORECASE,
)


def _extract_course_phrase(text: str) -> str | None:
    """Generic course-title extraction from labeled fields or completion
    phrases. Layout-independent; used for any text (PDF layer or OCR)."""
    m = _COURSE_LABEL_RE.search(text)
    if m:
        return m.group(1).strip().rstrip(" \t.:;,")[:120]
    m = _COURSE_PHRASE_RE.search(text)
    if m:
        return m.group(1).strip().rstrip(" \t.:;,")[:120]
    return None


_COURSE_STOP_LINES = (
    "awarded to", "presented to", "present this certificate to",
    "for successfully completing", "for completing", "completing the",
    "has completed", "successfully completed", "this certificate is awarded to",
    "this certifies that", "we hereby certify that", "we certify that",
)


def _extract_course_by_proximity(text: str, name: str | None, issuer: str | None) -> str | None:
    """Find the course block sitting directly above the certificate title.

    Real-world certificates commonly place the course/program name between the
    recipient and the certificate title line:
        Rohith Kumar K R
        Introduction to Software Engineering Job
        Simulation
        Certificate of Completion
    The block is collected as the consecutive title-cased lines above the first
    certificate-title line, bounded by the recipient name, the issuer, a
    recipient-verb line, or a full sentence. Returns ``None`` when the layout
    is not recognizably this shape.
    """
    lines = text.splitlines()
    title_idx = None
    for i, line in enumerate(lines):
        if _is_title_line(line):
            title_idx = i
            break
    if title_idx is None:
        return None

    name_low = (name or "").strip().lower()
    issuer_low = (issuer or "").strip().lower()
    parts: list[str] = []
    for j in range(title_idx - 1, -1, -1):
        cand = lines[j].strip().strip(".,;:\"'()")
        low = cand.lower()
        if not cand:
            continue
        if len(cand) > 120 or DATE_RE.search(cand):
            break
        if low in _COURSE_STOP_LINES:
            break
        if name_low and low == name_low:
            break
        if issuer_low and low == issuer_low:
            break
        if _is_title_line(cand) or _LABELED_LINE_RE.match(lines[j]):
            break
        first = cand[0]
        if not first.isupper() or cand.endswith((".", "!", "?")):
            break
        parts.append(cand)
    if not parts:
        return None
    course = " ".join(reversed(parts)).strip()
    if not (3 <= len(course) <= 120):
        return None
    return course

def extract_fields(text: str, allow_bare_name: bool = False) -> dict:
    """Extract structured fields from certificate text.

    ``allow_bare_name`` enables the OCR-derived fallbacks (standalone name
    line, course-title line) that are only reliable on OCR/layout text.
    """
    fields = {
        "cert_id": None,
        "candidate_name": None,
        "organization": None,
        "course": None,
        "issue_date": None,
        "marks_total": None,
        "marks_obtained": None,
        "grade": None,
        "has_signature": None,
        "has_seal": None,
        "has_qr": None,
        "has_url": None,
        "certificate_title": None,
        "verification_codes": None,
        "has_verification_code": None,
    }

    m = CERT_ID_RE.search(text)
    if m:
        fields["cert_id"] = m.group(0).upper()

    m = NAME_RE.search(text)
    if m:
        fields["candidate_name"] = m.group(1).strip()
    else:
        m = NAME_PRE_RE.search(text)
        if m and not _name_looks_organizational(m.group(1)):
            fields["candidate_name"] = m.group(1).strip()
        elif allow_bare_name or _certificate_like(text):
            fields["candidate_name"] = _extract_bare_name(text)

    m = GRADE_RE.search(text)
    if m:
        fields["grade"] = m.group(1).upper()

    m = MARKS_RE.search(text)
    if m:
        fields["marks_obtained"] = float(m.group(1))
        fields["marks_total"] = float(m.group(2))

    m = DATE_RE.search(text)
    if m:
        fields["issue_date"] = _normalize_date_match(m)

    low = text.lower()
    fields["organization"] = _extract_issuer(text)

    course = _extract_course_by_proximity(
        text, fields.get("candidate_name"), fields.get("organization")
    )
    if course is None:
        course = _extract_course_phrase(text)
    if course is None:
        for keyword in COURSE_KEYWORDS:
            if keyword in low:
                course = keyword.upper() if len(keyword) <= 4 else keyword.title()
                break
    if course is None and allow_bare_name:
        course = _extract_course_fallback(text, fields)
    fields["course"] = course

    for preferred in ("certificate", "certification"):
        for line in text.splitlines():
            if _is_title_line(line) == preferred:
                fields["certificate_title"] = line.strip()[:100]
                break
        if fields["certificate_title"]:
            break

    fields["has_signature"] = "signature" in low
    fields["has_seal"] = "seal" in low or "stamp" in low
    fields["has_qr"] = "qr" in low or "barcode" in low or "qrcode" in low
    fields["has_url"] = any(marker in low for marker in ["www.", "http://", "https://", ".com", "@mail"])

    codes, has_code = _extract_verification_codes(text)
    fields["verification_codes"] = codes
    fields["has_verification_code"] = has_code

    return fields


# --------------------------------------------------------------------------
# OCR helpers (Phase 10)
# --------------------------------------------------------------------------

def _render_pages(pdf: fitz.Document, dpi: int = 200, max_pages: int = 4) -> list[Image.Image]:
    """Render up to ``max_pages`` pages of a PDF to RGB images for OCR."""
    pages = []
    for page in pdf:
        if len(pages) >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi)
        pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
    return pages


def _ocr_pages(images: list[Image.Image]) -> tuple[list[str], list[float], int, bool]:
    """OCR a list of page images.

    Returns ``(texts, confidences, pages_processed, any_failed)``. Never
    raises; each page is best-effort.
    """
    texts: list[str] = []
    confidences: list[float] = []
    failed_pages = 0
    for img in images:
        result = ocr_image(img)
        if result.failed:
            failed_pages += 1
            continue
        if result.text.strip():
            texts.append(result.text.strip())
        if result.confidence is not None:
            confidences.append(result.confidence)
    any_failed = failed_pages > 0
    return texts, confidences, len(images), any_failed


def _confidence_level(confidence: float | None) -> str:
    """Map a numeric confidence to a coarse level for the UI."""
    if confidence is None:
        return "low"
    if confidence >= 0.7:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def extract_document(path: str, ext: str) -> ExtractionResult:
    if ext == "pdf":
        return _extract_pdf(path)
    return _extract_image(path)


def _extract_pdf(path: str) -> ExtractionResult:
    result = ExtractionResult(page_count=0)
    doc = fitz.open(path)
    result.page_count = doc.page_count
    pages_text = [page.get_text("text") for page in doc]
    embedded_text = "\n".join(pages_text).strip()

    try:
        img = _first_page_image(doc)
        result.visual = compute_visual(img)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not render PDF page: %s", exc)
        result.warnings.append("Could not render PDF for visual analysis.")

    result.text = embedded_text
    result.fields = extract_fields(embedded_text)
    result.extracted_text_length = len(embedded_text)
    result.extraction_completeness = _core_completeness(result.fields)

    sufficient = _text_sufficient(embedded_text, result.fields)
    if sufficient:
        result.extraction_method = "pdf_text"
        result.extraction_confidence = _pdf_text_confidence(result.fields)
    else:
        # Embedded text layer is insufficient -> OCR fallback (Phase 10).
        try:
            ocr_images = _render_pages(doc, dpi=settings.ocr_dpi, max_pages=settings.ocr_max_pages)
        except Exception as exc:  # noqa: BLE001 - OCR must fail gracefully
            logger.warning("Could not render PDF for OCR: %s", exc)
            ocr_images = []
            result.warnings.append("Could not render PDF pages for OCR.")

        if ocr_images:
            ocr_texts, ocr_confidences, pages_done, any_failed = _ocr_pages(ocr_images)
            result.ocr_pages = pages_done
            result.ocr_failed = any_failed or not ocr_texts
            ocr_text = "\n".join(ocr_texts).strip()
            if ocr_text:
                result.ocr_used = True
                if embedded_text:
                    combined = embedded_text + "\n" + ocr_text
                    method = "hybrid"
                else:
                    combined = ocr_text
                    method = "ocr"
                result.text = combined
                result.fields = extract_fields(combined, allow_bare_name=True)
                result.extracted_text_length = len(combined)
                result.extraction_completeness = _core_completeness(result.fields)
                result.extraction_method = method
                result.extraction_confidence = round(
                    min((sum(ocr_confidences) / len(ocr_confidences)) if ocr_confidences else 0.5, 0.95),
                    4,
                )
            else:
                result.ocr_failed = True
                result.warnings.append(
                    "Low extraction confidence — manual review recommended: OCR could not "
                    "recover text from the rendered document pages."
                )
                result.extraction_method = "pdf_text" if embedded_text else "none"
                result.extraction_confidence = _pdf_text_confidence(result.fields) if embedded_text else 0.0
        else:
            result.ocr_failed = True
            result.warnings.append(
                "Low extraction confidence — manual review recommended: the embedded text "
                "layer is insufficient and OCR was unavailable."
            )
            result.extraction_method = "pdf_text" if embedded_text else "none"
            result.extraction_confidence = _pdf_text_confidence(result.fields) if embedded_text else 0.0

    if not result.text:
        result.warnings.append("No text could be extracted from this document (scanned or blank).")

    doc.close()
    return result


def _pdf_text_confidence(fields: dict) -> float:
    """Confidence of a text-layer-only extraction, based on how much of the
    expected certificate structure was recovered (0.6..0.95)."""
    completeness = _core_completeness(fields)
    return round(min(0.6 + 0.4 * completeness, 0.95), 4)


def _extract_image(path: str) -> ExtractionResult:
    result = ExtractionResult(page_count=1)
    img = Image.open(path)
    img.load()
    result.visual = compute_visual(img)

    result.ocr_pages = 1
    ocr = ocr_image(img)
    if ocr.failed:
        result.ocr_failed = True
        result.warnings.append(
            "Low extraction confidence — manual review recommended: OCR could not "
            "recover text from this image."
        )
        result.extraction_method = "none"
        result.extraction_confidence = 0.0
    else:
        result.ocr_used = True
        result.text = ocr.text.strip()
        result.extracted_text_length = len(result.text)
        result.extraction_method = "ocr"
        result.extraction_confidence = round(min(ocr.confidence or 0.5, 0.95), 4)
        if not result.text:
            result.ocr_failed = True
            result.warnings.append(
                "Low extraction confidence — manual review recommended: OCR recovered no text."
            )

    result.fields = extract_fields(result.text, allow_bare_name=True)
    result.extraction_completeness = _core_completeness(result.fields)
    return result
