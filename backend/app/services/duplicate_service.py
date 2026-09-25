"""Duplicate / reuse detection (Phase 8D).

Builds safe document fingerprints from content hashing and extracted identity
fields, and checks them against prior verifications.

Fingerprint types:
  - file: SHA-256 of the uploaded content (exact same file)
  - cert_id: normalized certificate ID (same certificate ID)
  - identity: recipient + issuer + course + date (only when ALL are present)

Two different legitimate certificates belonging to the same person are NOT
flagged because the identity fingerprint requires the full combination to
match.
"""

import hashlib
import re

from sqlalchemy.orm import Session

from app.models.verification import Verification

_WHITESPACE = re.compile(r"\s+")
_ID_NORMALIZE = re.compile(r"[^A-Z0-9-]")


def _normalize(value) -> str:
    if not value:
        return ""
    return _WHITESPACE.sub(" ", str(value).strip()).lower()


def file_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def cert_id_fingerprint(cert_id) -> str | None:
    if not cert_id or not str(cert_id).strip():
        return None
    return _ID_NORMALIZE.sub("", str(cert_id).upper())


def identity_fingerprint(fields: dict) -> str | None:
    """Fingerprint of (recipient, issuer, course, date). Requires all present."""
    recipient = _normalize(fields.get("candidate_name"))
    issuer = _normalize(fields.get("organization"))
    course = _normalize(fields.get("course"))
    issue_date = _normalize(fields.get("issue_date"))
    if not (recipient and issuer and course and issue_date):
        return None
    return hashlib.sha256(
        "|".join([recipient, issuer, course, issue_date]).encode("utf-8")
    ).hexdigest()


# Priority order: exact file match is the strongest signal.
_FP_ORDER = ("file", "cert_id", "identity")


def _match_prior(
    db: Session,
    fingerprints: dict,
    exclude_id: int | None = None,
    user_id: str | None = None,
):
    """Return (duplicate_of_verification_id, duplicate_type) or (None, None).

    Scoped to ``user_id`` so duplicate signals only ever reference the acting
    user's own verifications (legacy pre-auth rows with NULL user_id are never
    matched, and no cross-user leakage happens).
    """
    query = db.query(Verification).filter(
        Verification.prediction != "error",
    )
    if user_id is not None:
        query = query.filter(Verification.user_id == user_id)
    rows = query.all()
    for fp_type in _FP_ORDER:
        fp_value = fingerprints.get(fp_type)
        if not fp_value:
            continue
        for row in rows:
            if exclude_id is not None and row.id == exclude_id:
                continue
            stored = getattr(row, f"{fp_type}_fingerprint", None)
            if stored and stored == fp_value:
                return row.verification_id, fp_type
    return None, None


def find_duplicate(
    db: Session,
    content: bytes,
    fields: dict,
    exclude_id: int | None = None,
    user_id: str | None = None,
) -> dict:
    """Check a new verification against the acting user's prior verifications.

    Returns:
      {"is_duplicate": bool,
       "duplicate_of": verification_id | None,
       "duplicate_type": "file" | "cert_id" | "identity" | None}
    """
    fingerprints = {
        "file": file_fingerprint(content),
        "cert_id": cert_id_fingerprint(fields.get("cert_id")),
        "identity": identity_fingerprint(fields),
    }
    duplicate_of, duplicate_type = _match_prior(db, fingerprints, exclude_id, user_id)
    return {
        "is_duplicate": duplicate_of is not None,
        "duplicate_of": duplicate_of,
        "duplicate_type": duplicate_type,
    }