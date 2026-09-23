"""Generate the EXTERNAL VALIDATION set for the v2 generalization study.

These documents are HELD OUT from training: they are never added to
data/raw or data/processed and are used only to probe how random_forest_v2
generalizes to certificate styles that differ from the training generator.

IMPORTANT:
- All generated PDFs are SYNTHETIC and labelled as such in the manifest.
  They must never be presented as real documents.
- Layouts, phrasing, date formats, ID schemes and decorations deliberately
  differ from src/data/make_dataset.py templates.
- One REAL-WORLD document (the AWS Training & Certification completion
  certificate) and two project sample PDFs are copied in so the set includes
  non-synthetic examples; the manifest records their source.

Output: backend/external_validation/{category}/*.pdf + manifest.json
"""

import json
import pathlib
import shutil
import sys

import pymupdf as fitz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.data import certificate_patterns as cp  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "external_validation"
UPLOADS = ROOT / "uploads"
SAMPLES = ROOT / "samples"
W, H = 612, 792


def new_page():
    doc = fitz.open()
    return doc, doc.new_page(width=W, height=H)


def save(doc, name):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return name


def border(page, margin=40, width=2.0):
    page.draw_rect(fitz.Rect(margin, margin, W - margin, H - margin), color=(0, 0, 0), width=width)
    m = margin + 8
    page.draw_rect(fitz.Rect(m, m, W - m, H - m), color=(0, 0, 0), width=0.75)


def hline(page, y, x0=80, x1=W - 80, width=1.0):
    page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), color=(0, 0, 0), width=width)


def center(page, rect, text, size=16, font="helv"):
    page.insert_textbox(fitz.Rect(*rect), text, fontsize=size, fontname=font,
                        align=fitz.TEXT_ALIGN_CENTER)


def block(page, rect, text, size=12, font="helv"):
    page.insert_textbox(fitz.Rect(*rect), text, fontsize=size, fontname=font,
                        lineheight=1.2)


def rows(page, y, lines, size=11, font="helv"):
    for line in lines:
        if not line.strip():
            y += 16
            continue
        page.insert_text((95, y), line, fontsize=size, fontname=font)
        y += 17
    return y


def valid_cert_id(year, base5):
    return f"CERT-{year}-{base5}{cp.checksum_digit(base5)}"


# --------------------------------------------------------------------------
# Template builders (distinct layouts per category)
# --------------------------------------------------------------------------

def academic_style(name, course, grade, year, cert_id, date_str, issuer, title):
    doc, page = new_page()
    border(page)
    hline(page, 120)
    center(page, (90, 150, W - 90, 200), issuer, size=18)
    center(page, (90, 205, W - 90, 245), title, size=14)
    hline(page, 260)
    block(page, (110, 300, W - 110, 430),
          f"This certifies that {name}\nhas successfully fulfilled the requirements of the "
          f"{course} program and has been awarded the grade {grade}.",
          size=13, font="tiro")
    rows(page, 500, [
        f"Certificate Reference : {cert_id}",
        f"Marks : 91 out of 100",
        f"Date of Issue : {date_str}",
        f"Issued by : {issuer}",
        "Seal : embossed institutional seal",
        "Signature : Dean of Studies",
    ])
    center(page, (90, H - 110, W - 90, H - 80), "Verified electronically", size=9)
    doc.set_metadata({"title": f"{title} - {issuer}"})
    return save(doc, f"academic/{name.split()[-1].lower()}_{cert_id[-6:]}.pdf")


def completion_style(name, course, year, cert_id, date_str, provider, title):
    doc, page = new_page()
    border(page, width=1.2)
    center(page, (60, 120, W - 60, 165), provider, size=16)
    center(page, (60, 170, W - 60, 210), title, size=15)
    hline(page, 235)
    block(page, (90, 270, W - 90, 360),
          f"Awarded to {name}\nSuccessfully completed the {course} program\n"
          f"Certificate No. {cert_id}\nDate {date_str}",
          size=13)
    rows(page, 560, [
        f"Issued by {provider}",
        "Signature : Course Director",
    ])
    return save(doc, f"completion/{name.split()[-1].lower()}_{cert_id[-6:]}.pdf")


def training_style(name, course, hours, date_str, provider, title):
    doc, page = new_page()
    border(page, width=1.0)
    center(page, (60, 130, W - 60, 180), title, size=16, font="cour")
    center(page, (60, 185, W - 60, 215), provider, size=12, font="cour")
    hline(page, 250)
    block(page, (95, 290, W - 95, 400),
          f"This certifies that {name}\nhas completed {hours} contact hours of professional "
          f"development in\n{course}.",
          size=13, font="cour")
    rows(page, 540, [
        f"Training provider : {provider}",
        f"Completion date : {date_str}",
        "Authorized by : Head of Learning & Development",
    ])
    return save(doc, f"training/{name.split()[-1].lower()}_{hours}.pdf")


def online_style(name, course, year, cert_id, date_str, platform, title):
    doc, page = new_page()
    border(page, width=1.0)
    center(page, (60, 140, W - 60, 185), title, size=16, font="tiro")
    center(page, (60, 190, W - 60, 220), platform, size=12, font="tiro")
    hline(page, 255)
    block(page, (95, 300, W - 95, 400),
          f"We are pleased to present this certificate to {name}\nfor completing all "
          f"assignments and assessments in\n{course}.",
          size=13, font="tiro")
    rows(page, 545, [
        f"Certificate ID : {cert_id}",
        f"Date of Completion : {date_str}",
        "Awarded by the course faculty",
    ])
    return save(doc, f"online/{name.split()[-1].lower()}_{cert_id[-6:]}.pdf")


def technical_style(name, course, year, code, date_str, vendor, title):
    doc, page = new_page()
    border(page, width=2.0)
    center(page, (60, 150, W - 60, 200), vendor, size=17)
    center(page, (60, 205, W - 60, 245), title, size=14)
    hline(page, 275)
    block(page, (95, 310, W - 95, 420),
          f"This is to certify that {name}\nhas demonstrated proficiency in {course} and is "
          f"certified by {vendor}.",
          size=13)
    rows(page, 540, [
        f"Certification code : {code}",
        f"Date of Certification : {date_str}",
        "Verification code embedded",
    ])
    return save(doc, f"technical/{name.split()[-1].lower()}_{code[-6:]}.pdf")


def workshop_style(name, course, date_str, organizer, venue, title):
    doc, page = new_page()
    border(page, width=1.0)
    center(page, (60, 150, W - 60, 200), title, size=15, font="cour")
    center(page, (60, 205, W - 60, 240), organizer, size=12, font="cour")
    hline(page, 270)
    block(page, (95, 310, W - 95, 420),
          f"We thank {name}\nfor active participation in the {course}\nconducted on "
          f"{date_str} at {venue}.",
          size=13, font="cour")
    rows(page, 540, [
        f"Organized by : {organizer}",
        "Coordinator : Workshop Committee",
    ])
    return save(doc, f"workshop/{name.split()[-1].lower()}_participation.pdf")


# --------------------------------------------------------------------------
# Fraud builder: start from a template's raw lines, then inject violations
# --------------------------------------------------------------------------

def fraud_pdf(category, name, lines, title="Certificate"):
    doc, page = new_page()
    border(page, width=1.0)
    center(page, (60, 130, W - 60, 175), title, size=15)
    hline(page, 200)
    rows(page, 250, lines)
    return save(doc, f"{category}/fraud_{name}.pdf")


def blankish_pdf(category, name):
    doc, page = new_page()
    page.insert_text((120, 400), " ", fontsize=8)
    return save(doc, f"{category}/fraud_{name}.pdf")


MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}

    def reg(name, category, expected, source, note):
        manifest[name] = {"category": category, "expected": expected,
                          "source": source, "note": note}

    def g(name, category, expected, note, source="synthetic"):
        reg(name, category, expected, source, note)

    # ---------------- academic (university) ----------------
    n = academic_style("Emma Richardson", "Data Science", "A", 2023,
                       valid_cert_id(2023, "48291"), "July 12, 2023",
                       "University of Oxford", "Certificate of Achievement")
    g(n, "academic", "genuine", "centered layout, Times body, valid CERT id + checksum, seal/signature text")
    n = academic_style("Arjun Deshpande", "Mechanical Engineering", "B", 2022,
                       valid_cert_id(2022, "50176"), "5 March 2022",
                       "Imperial College London", "Certificate of Merit")
    g(n, "academic", "genuine", "day-month-year date format, valid id")

    n = fraud_pdf("academic", "degree_mill", [
        "FAKE UNIVERSITY DIPLOMA MILLS INC",
        "Get your degree instantly, no classes required.",
        "Buy verified certificates online. Pay now and receive within 24 hours.",
        "Student: John Smith",
        "ID: FREEDEG-2024-666666",
        "Date of Issue: 2035-01-01",
    ], title="Instant Degree Certificate")
    g(n, "academic", "suspicious", "unknown issuer, suspicious text, bad id, future date")
    n = fraud_pdf("academic", "mark_stuff", [
        "Certificate of Achievement",
        "This certifies that Jane Doe has completed the Computer Science program.",
        "Marks: 250 out of 100",
        "Grade: A",
        "ID: CERT-2024-999999",
        "Date: 2024-13-45",
    ])
    g(n, "academic", "suspicious", "marks exceed total, invalid month/day in date, invalid checksum id")

    # ---------------- completion (corporate) ----------------
    n = completion_style("Sara Mitchell", "Cloud Computing", 2024, "CMP-2024-11472",
                         "14 February 2024", "CogniTech Solutions", "Certificate of Completion")
    g(n, "completion", "genuine", "awarded-to phrasing, day-month-year date, no marks/qr/seal")
    n = completion_style("Daniel Okafor", "Project Management", 2025, "CMP-2025-22931",
                         "2025.03.02", "NovaSkills", "Completion Certificate")
    g(n, "completion", "genuine", "dot-separated date format (not parseable), completion title")

    n = fraud_pdf("completion", "instant_cert", [
        "Instant Cert Store",
        "Certificate of Completion",
        "Buy a completion certificate for $19, delivered instantly.",
        "Visit www.instantcertstore.com to order.",
        "Awarded to Someone Random",
        "Date: 2030-12-12",
    ])
    g(n, "completion", "suspicious", "suspicious text + url, future date, unknown issuer")
    n = blankish_pdf("completion", "empty_completion")
    g(n, "completion", "suspicious", "blank document, no extractable fields")

    # ---------------- training (professional) ----------------
    n = training_style("Lucas Ferreira", "Leadership", 40, "September 3, 2024",
                       "Peak Performance Academy", "Professional Training Certificate")
    g(n, "training", "genuine", "hours-based wording, courier font, no marks")
    n = training_style("Amara Osei", "Digital Marketing", 24, "22 August 2024",
                       "TechEdge Training", "Training Certificate")
    g(n, "training", "genuine", "day-month-year date, training title")

    n = fraud_pdf("training", "pay_now", [
        "Unaccredited fast track training, pay now and receive within 24 hours.",
        "Get your Leadership certificate free, contact us on whatsapp @trainer.",
        "No exam needed.",
        "Date: 2024/06/30",
    ])
    g(n, "training", "suspicious", "suspicious text, no recipient, unknown issuer")
    n = fraud_pdf("training", "no_date", [
        "Professional Training Certificate",
        "This certifies that Rahul Verma has completed 30 hours of Cloud Computing training.",
        "Issued by: FastCert Training",
    ], title="Training Certificate")
    g(n, "training", "suspicious", "no date, unknown issuer")

    # ---------------- online (online course) ----------------
    n = online_style("Maya Patel", "Web Development", 2024, "ONL-2024-33018",
                     "April 3, 2024", "EduStream", "Course Certificate")
    g(n, "online", "genuine", "platform style, month-day-year date, no signature/seal/qr")
    n = online_style("Noah Berg", "Machine Learning", 2025, "ONL-2025-44102",
                     "2025/05/19", "LearnSphere", "Certificate of Completion")
    g(n, "online", "genuine", "slash ISO date, online platform")

    n = fraud_pdf("online", "free_cert", [
        "Course Certificate",
        "No classes required. Purchase a Machine Learning certificate by clicking here.",
        "www.cheapcerts.biz",
        "Date: 2026-01-15",
    ])
    g(n, "online", "suspicious", "suspicious text + url, future date, no recipient")
    n = fraud_pdf("online", "bare_bones", [
        "Certificate",
        "This certifies that someone completed something.",
    ])
    g(n, "online", "suspicious", "missing course/date/issuer/title fields")

    # ---------------- technical (vendor certification) ----------------
    n = technical_style("Ibrahim Suleiman", "Cybersecurity", 2024, "TECH-2024-0881",
                        "11 November 2024", "SecurEdge Labs", "Technical Certification")
    g(n, "technical", "genuine", "vendor phrasing, competency wording, no marks")
    n = technical_style("Hannah Kim", "AWS", 2025, "TECH-2025-1732",
                        "2025-06-08", "CloudForge Academy", "Certification of Competency")
    g(n, "technical", "genuine", "iso date, competency in AWS")

    n = fraud_pdf("technical", "for_sale", [
        "Certifications for sale, verified by nobody. Call 1-900-CERT-FAKE.",
        "Get your AWS certificate free, contact us on whatsapp @certking.",
        "Date: 2020-01-01",
    ])
    g(n, "technical", "suspicious", "suspicious text, no recipient, unknown vendor")
    n = fraud_pdf("technical", "bad_course", [
        "Technical Certification",
        "This certifies that Kevin Zhao has demonstrated proficiency in Quantum Arcana Forecasting.",
        "ID: XYZ-999",
        "Date: 2024/11/03",
    ])
    g(n, "technical", "suspicious", "course not in keyword list, bad id, no issuer")

    # ---------------- workshop (workshop/seminar) ----------------
    n = workshop_style("Fatima Noor", "Communication Skills", "19 June 2024",
                       "NovaSkills", "City Convention Centre", "Workshop Certificate")
    g(n, "workshop", "genuine", "attendance wording, day-month-year date, no marks")
    n = workshop_style("Tom Bakker", "Leadership", "October 25, 2024",
                       "Lumina Professional", "Grand Plaza Hotel", "Seminar Participation Certificate")
    g(n, "workshop", "genuine", "seminar attendance wording")

    n = fraud_pdf("workshop", "shady_seminar", [
        "Certificate for sale, pay now, get attendance credits instantly.",
        "www.fakeseminars.org",
        "Date: 2024/01/01",
    ])
    g(n, "workshop", "suspicious", "suspicious text + url, no recipient/issuer")
    n = blankish_pdf("workshop", "blank_attendance")
    g(n, "workshop", "suspicious", "blank document, missing all fields")

    # ---------------- non-synthetic documents ----------------
    aws_src = list(UPLOADS.glob("52e3ce2100a04b8a8324e14d0f83a416.pdf"))
    if aws_src:
        shutil.copy(aws_src[0], OUT / "completion" / "aws_completion_certificate.pdf")
        reg("completion/aws_completion_certificate.pdf", "completion", "genuine",
            "real-world", "AWS Training & Certification completion certificate (external, not in training)")

    if (SAMPLES / "genuine_certificate.pdf").exists():
        shutil.copy(SAMPLES / "genuine_certificate.pdf",
                    OUT / "academic" / "project_sample_genuine.pdf")
        reg("academic/project_sample_genuine.pdf", "academic", "genuine",
            "project-sample", "project sample (synthetic, generator-style University of Cambridge)")

    if (SAMPLES / "inconsistent_certificate.pdf").exists():
        shutil.copy(SAMPLES / "inconsistent_certificate.pdf",
                    OUT / "academic" / "project_sample_inconsistent.pdf")
        reg("academic/project_sample_inconsistent.pdf", "academic", "suspicious",
            "project-sample", "project sample (synthetic, generator-style fraud)")

    with open(OUT / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    total = len(manifest)
    print(f"Wrote {total} external validation documents to {OUT}")
    by_cat = {}
    for name, m in manifest.items():
        by_cat.setdefault(m["category"], []).append(m["expected"])
    for cat, exp in sorted(by_cat.items()):
        print(f"  {cat:<12} {len(exp)} docs (genuine={exp.count('genuine')} suspicious={exp.count('suspicious')})")


if __name__ == "__main__":
    main()