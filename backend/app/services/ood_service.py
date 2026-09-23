"""Out-of-distribution / anomaly advisory signal (Phase 9F).

Produces an advisory ``ood_status`` for a verified certificate:

  - ``normal``                  the document is well inside the expected range
  - ``unusual``                 the document deviates from the expected
                                certificate patterns in some observable way
  - ``insufficient_information`` the document could not be read well enough
                                to make a judgement

The signal is computed ONLY from existing intelligence/structural information
(certificate type, extraction completeness, issuer recognition, structural
completeness, feature-derived indicators, unusual type combinations). It is
NEVER added to the 31 ML features, NEVER used to change the ML prediction, and
must NEVER be described as proof of fraud. It is an advisory routing signal for
human reviewers.
"""

# Structure-completeness below this is an "unusual" structural deviation.
_STRUCTURE_UNUSUAL = 0.4
# Extraction completeness below this means there is too little to judge.
_EXTRACTION_INSUFFICIENT = 0.2


def _extraction_completeness(fields: dict) -> float:
    """Fraction of the 5 core identity fields that are present (0..1)."""
    keys = ("candidate_name", "organization", "course", "issue_date", "cert_id")
    present = sum(1 for k in keys if fields.get(k) and str(fields.get(k)).strip())
    return present / len(keys)


def _unusual_type_combination(flags: dict) -> bool:
    """Flag unusual certificate-type combinations.

    Examples: a document flagged both academic and online (an "online degree"),
    or academic + workshop. These combinations are possible in reality but are
    structurally unusual and worth a reviewer's attention.
    """
    if not isinstance(flags, dict):
        return False
    academic = bool(flags.get("academic"))
    online = bool(flags.get("online"))
    workshop = bool(flags.get("workshop"))
    suspicious_words = bool(flags.get("suspicious_keywords"))
    if academic and online:
        return True
    if academic and workshop:
        return True
    if online and suspicious_words:
        return True
    return False


def compute_ood_status(intelligence: dict, extraction, features: dict) -> str:
    """Return one of ``normal`` | ``unusual`` | ``insufficient_information``.

    Parameters mirror the objects already available in the intelligence layer so
    this runs at verification time with no extra extraction pass.
    """
    fields = extraction.fields or {}
    text = (extraction.text or "").strip()

    completeness = _extraction_completeness(fields)

    # Not enough information to judge: no text and essentially no fields.
    if not text and completeness < _EXTRACTION_INSUFFICIENT:
        return "insufficient_information"

    flags = intelligence.get("certificate_type", {}).get("flags", {})
    primary = intelligence.get("certificate_type", {}).get("primary", "unknown")
    structure = float(intelligence.get("structure_completeness") or 0.0)
    issuer_status = intelligence.get("issuer_status")
    quality = intelligence.get("quality_indicators") or {}
    findings = intelligence.get("consistency_findings") or []

    if primary == "unknown":
        return "unusual"
    if structure < _STRUCTURE_UNUSUAL:
        return "unusual"
    if issuer_status == "warning":
        return "unusual"
    if _unusual_type_combination(flags):
        return "unusual"
    if quality.get("blank_document"):
        return "unusual"
    if quality.get("color_anomaly") and not quality.get("text_present"):
        return "unusual"
    # Any high-severity consistency finding (marks > total, invalid cert ID,
    # suspicious wording, future date...) marks the document as unusual.
    if any(f.get("severity") == "high" for f in findings):
        return "unusual"
    # Feature-derived unusual combination: risky wording + URL simultaneously.
    if int(features.get("suspicious_keyword_count", 0) or 0) > 0 and int(
        features.get("suspicious_url_present", 0) or 0
    ):
        return "unusual"

    return "normal"