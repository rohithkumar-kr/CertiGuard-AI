"""Generate reproducible sample certificate PDFs for development/testing.

ALL people, institutions and documents in these samples are FICTIONAL.
They are synthetic artifacts used to exercise the end-to-end verification
pipeline and must never be presented as real certificates.

Output: backend/samples/

Usage (from backend/):
    python scripts/generate_samples.py
"""

import argparse
import pathlib
import sys

import pymupdf as fitz

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.data import certificate_patterns as cp  # noqa: E402

SAMPLES_DIR = pathlib.Path(__file__).resolve().parent.parent / "samples"


def checksum_id(year: str, base5: str) -> str:
    return f"CERT-{year}-{base5}{cp.checksum_digit(base5)}"


def write_certificate(filename: str, title: str, subtitle: str, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.draw_rect(fitz.Rect(36, 36, 576, 756), color=(0, 0, 0), width=2)
    page.draw_rect(fitz.Rect(48, 48, 564, 744), color=(0, 0, 0), width=0.75)
    page.insert_textbox(fitz.Rect(72, 90, 540, 150), title,
                        fontsize=20, fontname="helv", align=1)
    if subtitle:
        page.insert_textbox(fitz.Rect(72, 150, 540, 185), subtitle,
                            fontsize=12, fontname="helv", align=1)

    y = 215
    for line in lines:
        if not line.strip():
            y += 18
            continue
        page.insert_text((72, y), line, fontsize=11, fontname="helv")
        y += 20

    doc.save(filename)
    doc.close()


def generate() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 1. Genuine certificate (fictional person, recognized institution)
    #    Consistent information, valid ID + checksum, security markers.
    #    The issuer is drawn from KNOWN_ISSUERS so the model's
    #    issuer_known feature evaluates as trusted.
    # ------------------------------------------------------------------ #
    genuine_id = checksum_id("2021", "48291")
    write_certificate(
        str(SAMPLES_DIR / "genuine_certificate.pdf"),
        "University of Cambridge",
        "Certificate of Achievement",
        [
            "",
            "This is to certify that Alexandra Carter has successfully completed",
            "the requirements of the Data Science program and has been awarded",
            "the grade A.",
            "",
            f"Certificate ID: {genuine_id}",
            "Marks Obtained: 92 out of 100",
            "Date of Issue: 2021-07-15",
            "Issued by: University of Cambridge",
            "Verification: QR code embedded on this certificate",
            "Signature: Professor H. Whitfield, Registrar",
            "Seal: Official University Seal",
        ],
    )

    # ------------------------------------------------------------------ #
    # 2. Suspicious certificate with inconsistent information
    #    Unknown issuer, invalid ID, marks exceeding total, future date,
    #    suspicious marketing text, no security markers.
    # ------------------------------------------------------------------ #
    write_certificate(
        str(SAMPLES_DIR / "inconsistent_certificate.pdf"),
        "QUICK DIPLOMAS LTD",
        "Instant Certificate",
        [
            "",
            "Buy verified certificates online. No exam needed, instant delivery.",
            "Get your Computer Science certificate free, contact us on whatsapp @certking.",
            "",
            "Candidate ID: FREECERT-2022-999999",
            "Marks: 150 out of 100",
            "Grade: A",
            "Issue Date: 2030-05-01",
        ],
    )

    # ------------------------------------------------------------------ #
    # 3. Suspicious certificate missing verification/security information
    #    Structured fields but no ID verification, signature, seal or QR.
    # ------------------------------------------------------------------ #
    missing_id = checksum_id("2019", "73124")
    write_certificate(
        str(SAMPLES_DIR / "missing_security_certificate.pdf"),
        "WINDSOR HEIGHTS COLLEGE",
        "Certificate of Completion",
        [
            "",
            "This is to certify that Rohan Mehta has completed the",
            "Electrical Engineering program.",
            "",
            f"Candidate ID: {missing_id}",
            "Marks: 74 out of 100",
            "Grade: B",
            "Issue Date: 2019-12-10",
            "",
            "No verification code is included with this document.",
        ],
    )

    # ------------------------------------------------------------------ #
    # 4. Unusual but internally valid formatting (case/whitespace noise)
    # ------------------------------------------------------------------ #
    unusual_id = checksum_id("2020", "50176")
    write_certificate(
        str(SAMPLES_DIR / "unusual_valid_certificate.pdf"),
        "CERTIFICATE",
        "",
        [
            "  from meridian institute of technology   ",
            "",
            "we hereby certify that Priya Nair completed the",
            "Information Technology program.",
            f"certificate id {unusual_id}   grade: B   82/100",
            "issued: 2020-03-09",
            "signed & sealed by the registrar",
        ],
    )

    # ------------------------------------------------------------------ #
    # 5. Incomplete certificate (almost no extractable information)
    # ------------------------------------------------------------------ #
    write_certificate(
        str(SAMPLES_DIR / "incomplete_certificate.pdf"),
        "Certificate",
        "",
        ["This document contains limited information."],
    )

    # ------------------------------------------------------------------ #
    # Failure-case inputs (rejected by validation / extraction)
    # ------------------------------------------------------------------ #
    (SAMPLES_DIR / "empty.pdf").write_bytes(b"")
    (SAMPLES_DIR / "malformed.pdf").write_bytes(b"%PDF-1.4\nbroken content\nnot a real pdf\n%%EOF")
    (SAMPLES_DIR / "unsupported.txt").write_bytes("plain text document".encode("utf-8"))
    # >10 MB so it exceeds the default size limit (MAX_UPLOAD_SIZE_MB=10).
    (SAMPLES_DIR / "oversized.pdf").write_bytes(b"%PDF-1.4" + b"\x00" * (11 * 1024 * 1024))

    print(f"Generated sample certificates in {SAMPLES_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate sample certificate PDFs")
    parser.add_argument("--output", type=pathlib.Path, default=None)
    args = parser.parse_args()
    if args.output:
        SAMPLES_DIR = args.output  # noqa: PLW0603
    generate()