"""Manual-review prioritization (Phase 9G).

Computes a ``review_priority`` (``low`` | ``medium`` | ``high``) used ONLY to
route human reviewers toward the documents that most need a decision.

It is based on:
  - risk score (the unchanged ML risk score)
  - consistency findings (severity / count)
  - duplicate findings
  - the OOD advisory signal
  - extraction completeness
  - certificate structure completeness

The priority NEVER alters the ML prediction, the risk score, or the review
status band. It is a separate, advisory triage label.
"""

REVIEW_PRIORITIES = ("low", "medium", "high")

_HIGH_SEVERITY_KEYS = {
    "marks_exceed_total",
    "invalid_date",
    "invalid_cert_id",
    "grade_marks_mismatch",
    "suspicious_wording",
    "suspicious_url",
}
_MEDIUM_KEYS = {
    "missing_recipient",
    "low_structure",
    "unknown_issuer",
    "cert_id_issuer_mismatch",
    "invalid_marks",
    "missing_text",
    "visual_quality",
}
# Score band where manual triage is clearly warranted regardless of signals.
_MEDIUM_RISK_MIN = 0.30
_HIGH_RISK_MIN = 0.50


def _severity_of(finding: dict) -> str:
    return finding.get("severity", "medium")


def compute_review_priority(
    risk_score: float,
    review_status: str,
    consistency_findings: list,
    duplicate: dict,
    ood_status: str,
    extraction_completeness: float,
    structure_completeness: float,
) -> str:
    """Return ``low`` | ``medium`` | ``high`` (advisory triage, not prediction)."""
    duplicate_info = duplicate or {}
    findings = list(consistency_findings or [])

    # --- High priority: unambiguous triage triggers ---
    if duplicate_info.get("is_duplicate"):
        return "high"
    if review_status == "high_risk" or risk_score >= _HIGH_RISK_MIN:
        return "high"
    if any(f.get("key") in _HIGH_SEVERITY_KEYS for f in findings):
        return "high"
    if ood_status == "unusual":
        return "high"
    if structure_completeness < 0.4:
        return "high"

    # --- Medium priority: needs a human look but is not urgent ---
    if risk_score >= _MEDIUM_RISK_MIN or review_status == "manual_review":
        return "medium"
    high = [f for f in findings if _severity_of(f) == "high"]
    medium = [f for f in findings if _severity_of(f) == "medium"]
    if len(high) + len(medium) >= 2:
        return "medium"
    if any(f.get("key") in _MEDIUM_KEYS for f in findings):
        return "medium"
    if ood_status == "insufficient_information":
        return "medium"
    if extraction_completeness < 0.6:
        return "medium"

    # --- Low priority: nothing pressing ---
    return "low"