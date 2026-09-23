"""Certificate consistency engine (Phase 8E).

Compares the extracted identity fields and detects internal contradictions
(e.g. grade B but 91/100, future issue date, marks above total, missing
recipient, certificate ID inconsistent with the issuer format).

Findings are structured, feed the explanation / manual-review layer, and NEVER
alter the production ML model. Missing fields are reported as missing, not as
fraud.
"""

from datetime import date, datetime

import re

from src.data import certificate_patterns as cp

from app.services.extraction_service import ExtractionResult

# Checksum-valid certificate IDs follow the synthetic CERT-YYYY-NNNNNN format.
_STANDARD_CERT_ID_RE = cp.CERT_ID_REGEX


def _parse_issue_date(value) -> date | None:
    if not value:
        return None
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


def _grade_band_ok(grade: str | None, marks_total, marks_obtained) -> tuple[bool, str]:
    """Return (ok, detail) for grade/marks consistency, or (True, '') when the
    data needed for the check is not available."""
    if not grade:
        return True, ""
    try:
        total = float(marks_total)
        obtained = float(marks_obtained)
    except (TypeError, ValueError):
        return True, ""
    if total <= 0:
        return True, ""
    pct = obtained / total * 100
    expected = cp.grade_band(pct)
    ok = cp.grade_consistent(grade, pct)
    return ok, f"grade {grade.upper()} does not match the expected band for {pct:.0f}% (expected {expected})."


def _cert_id_status(cert_id: str | None) -> tuple[str, str]:
    """Return (status, detail) for a certificate ID.

    status is one of 'ok' | 'missing' | 'warning'.
    """
    if not cert_id or not str(cert_id).strip():
        return "missing", "No certificate ID detected."
    cert_id = str(cert_id).strip()
    if not _STANDARD_CERT_ID_RE.match(cert_id):
        return "warning", f"Certificate ID {cert_id} does not match the expected CERT-YYYY-NNNNNN format."
    if not cp.cert_id_checksum_valid(cert_id):
        return "warning", f"Certificate ID {cert_id} failed the format checksum."
    return "ok", f"Certificate ID {cert_id} detected and structurally valid."


def _issuer_status(issuer: str | None) -> tuple[str, str]:
    """Return (status, detail) for the issuer field."""
    if not issuer or not str(issuer).strip():
        return "missing", "No issuer / organization detected."
    if cp.issuer_known(str(issuer)):
        return "ok", f"Recognized issuer: {issuer}."
    return "warning", (
        f"Issuer '{issuer}' is not in the recognized issuer list. "
        "Real-world issuer verification may require external verification."
    )


def _date_status(issue_date: date | None) -> tuple[str, str]:
    """Return (status, detail) for the issue date."""
    if issue_date is None:
        return "missing", "No issue date detected."
    if not cp.issue_year_valid(issue_date.year):
        return "warning", f"Issue year {issue_date.year} is outside the expected range."
    if issue_date > date.today():
        return "warning", f"Issue date {issue_date.isoformat()} is in the future."
    return "ok", f"Issue date {issue_date.isoformat()} detected and consistent."


def build_consistency_findings(extraction: ExtractionResult) -> dict:
    """Build structured consistency findings for the intelligence layer.

    Returns a dict with:
      - identity: normalized per-field status
      - findings: list of {key, label, status, severity, detail}
    """
    fields = extraction.fields or {}
    text = extraction.text or ""

    cert_id = fields.get("cert_id")
    issuer = fields.get("organization")
    recipient = fields.get("candidate_name")
    course = fields.get("course")
    issue_date = _parse_issue_date(fields.get("issue_date"))
    grade = fields.get("grade")
    marks_total = fields.get("marks_total")
    marks_obtained = fields.get("marks_obtained")

    # --- Identity field statuses ---
    identity = {
        "recipient": {
            "label": "Recipient",
            "value": recipient,
            "present": bool(recipient and str(recipient).strip()),
        },
        "issuer": {
            "label": "Issuer",
            "value": issuer,
            "present": bool(issuer and str(issuer).strip()),
        },
        "course": {
            "label": "Course / Title",
            "value": course,
            "present": bool(course and str(course).strip()),
        },
        "issue_date": {
            "label": "Issue Date",
            "value": fields.get("issue_date"),
            "present": issue_date is not None,
        },
        "certificate_id": {
            "label": "Certificate ID",
            "value": cert_id,
            "present": bool(cert_id and str(cert_id).strip()),
        },
        "marks": {
            "label": "Marks / Grade",
            "value": (
                f"{marks_obtained} / {marks_total}" + (f" ({grade})" if grade else "")
                if marks_obtained is not None else (grade or None)
            ),
            "present": marks_obtained is not None or bool(grade),
        },
    }

    # --- Field-level statuses ---
    recipient_status = (
        ("ok", f"Recipient detected: {recipient}.")
        if identity["recipient"]["present"]
        else ("missing", "No recipient name detected.")
    )
    course_status = (
        ("ok", f"Course detected: {course}.")
        if identity["course"]["present"]
        else ("missing", "No course / title detected.")
    )
    cert_status, cert_detail = _cert_id_status(cert_id)
    issuer_status, issuer_detail = _issuer_status(issuer)
    date_status, date_detail = _date_status(issue_date)

    # --- Consistency checks ---
    findings = []

    if not identity["recipient"]["present"]:
        findings.append({
            "key": "missing_recipient", "label": "Missing recipient",
            "status": "attention", "severity": "medium",
            "detail": "No recipient name could be extracted. This may indicate a "
                      "poor-quality document or missing expected structure.",
        })

    if date_status == "warning":
        findings.append({
            "key": "invalid_date", "label": "Invalid issue date",
            "status": "attention", "severity": "high",
            "detail": date_detail,
        })

    # Marks above total.
    try:
        total_f = float(marks_total)
        obtained_f = float(marks_obtained)
        if total_f > 0 and obtained_f > total_f:
            findings.append({
                "key": "marks_exceed_total", "label": "Marks exceed total",
                "status": "attention", "severity": "high",
                "detail": f"Marks {obtained_f:.0f} are greater than the total {total_f:.0f}.",
            })
        elif total_f <= 0 and marks_obtained is not None:
            findings.append({
                "key": "invalid_marks", "label": "Invalid marks",
                "status": "attention", "severity": "medium",
                "detail": "Marks were detected but the total is missing or invalid.",
            })
    except (TypeError, ValueError):
        pass

    # Grade vs marks consistency.
    grade_ok, grade_detail = _grade_band_ok(grade, marks_total, marks_obtained)
    if not grade_ok:
        findings.append({
            "key": "grade_marks_mismatch", "label": "Inconsistent grade",
            "status": "attention", "severity": "high",
            "detail": grade_detail,
        })

    # Certificate ID validity.
    if cert_status == "warning":
        findings.append({
            "key": "invalid_cert_id", "label": "Invalid certificate ID",
            "status": "attention", "severity": "high",
            "detail": cert_detail,
        })
    # A labeled certificate-ID field exists in the text but no valid standard
    # ID was extracted (e.g. "FREECERT-2022-999999" or a free-form value).
    if cert_status == "missing" and not identity["certificate_id"]["present"]:
        labeled_id = re.search(
            r"(?i:candidate[ \t]+id|certificate[ \t]+id|cert[ \t]+no|certification[ \t]+code)"
            r"[ \t]*[:.][ \t]*([^\r\n]+)",
            text,
        )
        if labeled_id and labeled_id.group(1).strip():
            raw_id = labeled_id.group(1).strip()[:40]
            findings.append({
                "key": "invalid_cert_id", "label": "Invalid certificate ID",
                "status": "attention", "severity": "high",
                "detail": f"Certificate ID '{raw_id}' does not match the expected "
                          "CERT-YYYY-NNNNNN format.",
            })

    # Unknown issuer.
    if issuer_status == "warning":
        findings.append({
            "key": "unknown_issuer", "label": "Unknown issuer",
            "status": "attention", "severity": "medium",
            "detail": issuer_detail,
        })

    # Certificate ID inconsistent with issuer format (e.g. a university
    # certificate whose ID is not a standard CERT-YYYY-NNNNNN).
    if (
        identity["issuer"]["present"]
        and identity["certificate_id"]["present"]
        and cert_id
        and not _STANDARD_CERT_ID_RE.match(str(cert_id).strip())
    ):
        findings.append({
            "key": "cert_id_issuer_mismatch", "label": "Certificate ID vs issuer",
            "status": "attention", "severity": "medium",
            "detail": "The certificate ID format is not consistent with the issuer's "
                      "expected certificate structure.",
        })

    # Suspicious wording / external link.
    suspicious_count = cp.suspicious_keyword_count(text)
    if suspicious_count:
        findings.append({
            "key": "suspicious_wording", "label": "Suspicious wording",
            "status": "attention", "severity": "high",
            "detail": f"{suspicious_count} suspicious phrase(s) detected "
                      f"({', '.join(cp.SUSPICIOUS_KEYWORDS[:3])}).",
        })
    if cp.suspicious_url_present(text):
        findings.append({
            "key": "suspicious_url", "label": "Suspicious URL",
            "status": "attention", "severity": "high",
            "detail": "An external link / URL was detected in the document.",
        })

    structure_completeness = _fraction_present([recipient, issuer, course, cert_id, fields.get("issue_date")])
    if structure_completeness < 0.4:
        findings.append({
            "key": "low_structure", "label": "Missing expected structure",
            "status": "attention", "severity": "medium",
            "detail": "The document differs from the expected certificate structure "
                      f"(field completeness {structure_completeness:.0%}).",
        })

    # --- Per-field consistency checks (upgrade) ---
    # Explicit PASS/WARNING/FAIL per identity field so the evidence engine can
    # surface "PASS: Recipient consistency" alongside problem findings. Missing
    # fields are WARNING (an extraction limitation), never FAIL; a missing
    # field is never treated as fraud.
    checks: list[dict] = []
    checks.append({
        "key": "recipient_consistency",
        "label": "Recipient consistency",
        "status": "PASS" if identity["recipient"]["present"] else "WARNING",
        "severity": "low",
        "detail": recipient_status[1],
    })
    checks.append({
        "key": "issuer_consistency",
        "label": "Issuer consistency",
        "status": "PASS" if issuer_status == "ok" else ("WARNING" if issuer_status == "warning" else "WARNING"),
        "severity": "low" if issuer_status == "ok" else "medium",
        "detail": issuer_detail,
    })
    checks.append({
        "key": "date_consistency",
        "label": "Date consistency",
        "status": "PASS" if date_status == "ok" else ("FAIL" if date_status == "warning" else "WARNING"),
        "severity": "low" if date_status == "ok" else ("high" if date_status == "warning" else "medium"),
        "detail": date_detail,
    })
    checks.append({
        "key": "course_consistency",
        "label": "Course / title consistency",
        "status": "PASS" if identity["course"]["present"] else "WARNING",
        "severity": "low",
        "detail": course_status[1],
    })
    checks.append({
        "key": "certificate_id_consistency",
        "label": "Certificate ID consistency",
        "status": "PASS" if cert_status == "ok" else ("FAIL" if cert_status == "warning" else "WARNING"),
        "severity": "low" if cert_status == "ok" else ("high" if cert_status == "warning" else "medium"),
        "detail": cert_detail,
    })
    marks_ok = not any(
        f["key"] in ("marks_exceed_total", "grade_marks_mismatch", "invalid_marks")
        for f in findings
    )
    checks.append({
        "key": "marks_consistency",
        "label": "Marks / grade consistency",
        "status": "PASS" if marks_ok else "FAIL",
        "severity": "low" if marks_ok else "high",
        "detail": "Marks and grade are internally consistent." if marks_ok
                  else "Marks / grade values are internally inconsistent.",
    })
    checks.append({
        "key": "structure_consistency",
        "label": "Document structure consistency",
        "status": "PASS" if structure_completeness >= 0.6 else ("WARNING" if structure_completeness >= 0.4 else "WARNING"),
        "severity": "low" if structure_completeness >= 0.6 else "medium",
        "detail": (f"Field completeness {structure_completeness:.0%} — expected "
                   "certificate structure recovered." if structure_completeness >= 0.6
                   else f"Only {structure_completeness:.0%} of expected fields recovered."),
    })

    return {
        "identity": identity,
        "certificate_id_status": cert_status,
        "issuer_status": issuer_status,
        "date_status": date_status,
        "recipient_status": recipient_status[0],
        "course_status": course_status[0],
        "structure_completeness": round(structure_completeness, 4),
        "findings": findings,
        "checks": checks,
    }