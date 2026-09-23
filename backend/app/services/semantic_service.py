"""Credential semantics (Phase 12, M5).

Generic, text-based semantic understanding of a certificate. Works on any text
source (embedded PDF text, OCR, or hybrid) and is entirely issuer-independent.

Extracts:
  * the credential statement (what the document asserts),
  * the credential level (student / professional / etc.),
  * which semantic roles are present (completion, achievement, certification,
    training, participation, award),
  * evidence that the document is a verification credential with a verifier
    role (verification phrase / code / URL presence).

A document that states "completes a course" or "earns a credential" is a
credential — that is what it claims. Absence of any credential statement is
evidence of poor structure, not of fraud.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_COMPLETION = (
    "successfully completed", "has completed", "completed the course",
    "course completion", "completion of", "for successfully completing",
    "has successfully completed", "completing the",
)
_ACHIEVEMENT = (
    "has achieved", "has earned", "achieved", "earned", "accomplished",
    "has demonstrated", "has acquired",
)
_CERTIFICATION = (
    "certifies that", "certification", "is certified", "professional certification",
    "certified professional", "has been certified",
)
_TRAINING = ("training", "trained", "training program", "course of training")
_PARTICIPATION = ("participation", "participated", "attended", "was awarded for participation")
_AWARD = ("awarded", "is awarded", "award", "presented to", "is hereby awarded")
_CREDENTIAL = (
    "credential", "credentials", "badge", "micro-credential", "certificate of",
    "student level credential", "credential of",
)
_VERIFICATION = (
    "verify", "verification", "scan to verify", "verification code",
    "verification url", "verify at", "check authenticity",
)
_LEVEL_PATTERNS = [
    ("student_level", r"student[- ]level"),
    ("professional", r"professional"),
    ("associate", r"associate(?! level)"),
    ("advanced", r"advanced"),
    ("expert", r"expert"),
    ("fundamentals", r"fundamentals"),
    ("essentials", r"essentials"),
]


@dataclass
class SemanticReport:
    statements: list = field(default_factory=list)
    roles: dict = field(default_factory=dict)
    credential_level: str = "unknown"
    credential_statement_present: bool = False
    verification_present: bool = False
    signals: dict = field(default_factory=dict)


def _scan(role: str, phrases: tuple, text: str) -> list[str]:
    found = []
    low = text.lower()
    for phrase in phrases:
        if phrase in low:
            # Capture the sentence fragment around the phrase.
            idx = low.find(phrase)
            start = max(0, idx - 120)
            end = min(len(text), idx + len(phrase) + 120)
            found.append(text[start:end].replace("\n", " ").strip())
    return found


def extract_semantics(text: str) -> SemanticReport:
    report = SemanticReport()
    if not text or not text.strip():
        return report

    roles = {
        "completion": _scan("completion", _COMPLETION, text),
        "achievement": _scan("achievement", _ACHIEVEMENT, text),
        "certification": _scan("certification", _CERTIFICATION, text),
        "training": _scan("training", _TRAINING, text),
        "participation": _scan("participation", _PARTICIPATION, text),
        "award": _scan("award", _AWARD, text),
        "credential": _scan("credential", _CREDENTIAL, text),
    }
    report.roles = {k: bool(v) for k, v in roles.items()}
    for role, snippets in roles.items():
        for s in snippets[:3]:
            report.statements.append({"role": role, "phrase": s})

    verification = _scan("verification", _VERIFICATION, text)
    report.verification_present = bool(verification)
    report.credential_statement_present = any(report.roles.values())

    # Credential level.
    low = text.lower()
    level = "unknown"
    for lvl, pat in _LEVEL_PATTERNS:
        if re.search(pat, low):
            level = lvl
            break
    report.credential_level = level

    report.signals = {
        "role_count": sum(report.roles.values()),
        "has_verification_statement": report.verification_present,
        "level_indicators": [p[0] for p in _LEVEL_PATTERNS if re.search(p[1], low)],
    }
    return report