"""Verification audit trail / investigation timeline tests.

Covers the append-only event model, the recording service, the API endpoint
(``GET /api/verifications/{id}/audit``), the timeline produced by the full
pipeline, the failure path, the review-action event, issuer severity mapping,
and the guarantee that no raw verification codes leak into the trail.

The API-level tests deliberately upload uniquely generated PDFs (unique file
bytes, cert ids, and identities) so they never create fingerprint collisions
with the shared fixtures used by the rest of the suite, which rely on a shared
session database.
"""

import json
import uuid
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.models.audit import AuditEvent
from app.services import audit_service

FORAGE_RAW_CODES = {"sJLRwfFRRwiZ6mSZk", "69c683a40afbea3f2d948ab3"}


def _make_pdf(text: str) -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return bytes(data)


def _unique_completion_pdf(seed: str) -> bytes:
    return _make_pdf(
        f"CloudForge Academy\n"
        f"Technical Certification\n"
        f"\n"
        f"This certifies that Audit Person {seed} has demonstrated proficiency in Cloud Computing.\n"
        f"Certification Code: AUDIT-CERT-{uuid.uuid4().hex[:10]}\n"
        f"Issued by CloudForge Academy\n"
        f"Issue Date: 2024-03-10\n"
        f"Signature: ____________\n"
    )


def _forage_style_pdf() -> bytes:
    """A uniquely generated PDF that extracts issuer 'Forage' + two codes."""
    return _make_pdf(
        f"Forage\n"
        f"Job Simulation Certificate\n"
        f"\n"
        f"This certifies that Audit Tester {uuid.uuid4().hex[:6]} has completed the "
        f"Introduction to Software Engineering Job Simulation.\n"
        f"Program offered by Forage\n"
        f"Enrolment verification code: sJLRwfFRRwiZ6mSZk\n"
        f"User verification code: 69c683a40afbea3f2d948ab3\n"
        f"Candidate ID: AUDIT-FORAGE-{uuid.uuid4().hex[:8]}\n"
        f"Issue Date: 2026-01-15\n"
    )


@pytest.fixture(autouse=True)
def _ensure_tables():
    """Create tables for db_session-only tests (idempotent, mirrors startup)."""
    from app.database.database import init_db

    init_db()
    yield


# ---------------------------------------------------------------------------
# Service-level behaviour
# ---------------------------------------------------------------------------

def test_record_event_and_list_ordering(db_session):
    audit_service.record_event(
        db_session,
        verification_id="V-TEST-1",
        event_type=audit_service.EVENT_DOCUMENT_RECEIVED,
        title="Document received",
        details={"filename": "a.pdf"},
    )
    audit_service.record_event(
        db_session,
        verification_id="V-TEST-1",
        event_type=audit_service.EVENT_ML_ANALYSIS,
        title="ML model analysis completed",
        status=audit_service.STATUS_COMPLETED,
        details={"prediction": "genuine", "risk_score": 0.1},
    )
    audit_service.record_event(
        db_session,
        verification_id="V-TEST-1",
        event_type=audit_service.EVENT_FINAL_DECISION,
        title="Final decision",
        details={"decision": "VERIFIED"},
    )
    events = audit_service.list_audit_events(db_session, "V-TEST-1")
    assert [e.event_type for e in events] == [
        audit_service.EVENT_DOCUMENT_RECEIVED,
        audit_service.EVENT_ML_ANALYSIS,
        audit_service.EVENT_FINAL_DECISION,
    ]
    assert [e.id for e in events] == sorted(e.id for e in events)
    # Completed status -> success severity.
    assert events[0].severity == audit_service.SEVERITY_SUCCESS
    assert events[0].created_at is not None


def test_events_are_isolated_by_verification_id(db_session):
    audit_service.record_event(
        db_session, verification_id="V-ISO-A",
        event_type=audit_service.EVENT_DOCUMENT_RECEIVED, title="A",
    )
    audit_service.record_event(
        db_session, verification_id="V-ISO-B",
        event_type=audit_service.EVENT_ML_ANALYSIS, title="B",
    )
    a = audit_service.list_audit_events(db_session, "V-ISO-A")
    b = audit_service.list_audit_events(db_session, "V-ISO-B")
    assert len(a) == 1 and a[0].event_type == audit_service.EVENT_DOCUMENT_RECEIVED
    assert len(b) == 1 and b[0].event_type == audit_service.EVENT_ML_ANALYSIS


def test_record_event_masks_sensitive_details(db_session):
    audit_service.record_event(
        db_session,
        verification_id="V-MASK-1",
        event_type=audit_service.EVENT_ISSUER_ANALYSIS,
        title="Issuer verification analysis",
        details={"checked_identifier": "sJLRwfFRRwiZ6mSZk", "code": "69c683a40afbea3f2d948ab3"},
    )
    event = audit_service.list_audit_events(db_session, "V-MASK-1")[0]
    details = audit_service._parse_details(event.details)
    assert details["checked_identifier"] != "sJLRwfFRRwiZ6mSZk"
    assert details["code"] != "69c683a40afbea3f2d948ab3"
    assert "sJLRwfFRRwiZ6mSZk" not in (event.details or "")


def test_serialize_event_shape(db_session):
    audit_service.record_event(
        db_session,
        verification_id="V-SER-1",
        event_type=audit_service.EVENT_FINAL_DECISION,
        title="Final decision",
        stage="decision",
        description="Assessment REQUIRES_VERIFICATION.",
        severity=audit_service.SEVERITY_WARNING,
        details={"decision": "REQUIRES_VERIFICATION"},
    )
    event = audit_service.list_audit_events(db_session, "V-SER-1")[0]
    payload = audit_service.serialize_event(event)
    assert payload["verification_id"] == "V-SER-1"
    assert payload["event_type"] == audit_service.EVENT_FINAL_DECISION
    assert payload["stage"] == "decision"
    assert payload["severity"] == "warning"
    assert payload["details"] == {"decision": "REQUIRES_VERIFICATION"}
    assert payload["created_at"] is not None


def test_record_error_without_vid_uses_v_err_fallback(db_session):
    from app.api.routes import record_error
    from app.models.verification import Verification

    record_error(db_session, "broken.txt", AppError("boom"), verification_id=None)
    row = (
        db_session.query(Verification)
        .filter(Verification.filename == "broken.txt", Verification.prediction == "error")
        .first()
    )
    assert row is not None
    assert row.verification_id.startswith("V-ERR-")
    events = audit_service.list_audit_events(db_session, row.verification_id)
    assert len(events) == 1
    assert events[0].event_type == audit_service.EVENT_PIPELINE_FAILED
    assert events[0].severity == audit_service.SEVERITY_ERROR
    assert events[0].details and "pre_processing" in events[0].details


# ---------------------------------------------------------------------------
# API-level behaviour (uses uniquely generated PDFs)
# ---------------------------------------------------------------------------

def test_audit_endpoint_missing_verification_returns_error(client):
    resp = client.get("/api/verifications/DOES-NOT-EXIST/audit")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Verification not found."


def test_successful_verification_has_full_timeline(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("audit_completion.pdf", _unique_completion_pdf("timeline"), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text[:500]
    vid = resp.json()["verification_id"]

    audit = client.get(f"/api/verifications/{vid}/audit")
    assert audit.status_code == 200
    body = audit.json()
    assert body["verification_id"] == vid
    types = [e["event_type"] for e in body["events"]]

    expected = [
        audit_service.EVENT_DOCUMENT_RECEIVED,
        audit_service.EVENT_TEXT_EXTRACTION,
        audit_service.EVENT_FEATURE_EXTRACTION,
        audit_service.EVENT_ML_ANALYSIS,
        audit_service.EVENT_INTELLIGENCE_ANALYSIS,
        audit_service.EVENT_CONSISTENCY_ANALYSIS,
        audit_service.EVENT_FORENSICS_ANALYSIS,
        audit_service.EVENT_VISUAL_ANALYSIS,
        audit_service.EVENT_TAMPERING_ANALYSIS,
        audit_service.EVENT_ISSUER_ANALYSIS,
        audit_service.EVENT_VERIFICATION_CODE_ANALYSIS,
        audit_service.EVENT_EVIDENCE_FUSION,
        audit_service.EVENT_FINAL_DECISION,
    ]
    assert types == expected
    assert body["events"][-1]["event_type"] == audit_service.EVENT_FINAL_DECISION
    assert body["events"][-1]["details"]["decision"] == resp.json()["decision"]
    # Every event carries the shared verification id.
    assert all(e["verification_id"] == vid for e in body["events"])


def test_failed_verification_records_failure_event(client):
    resp = client.post("/api/verify", files={"file": ("x.txt", b"not a pdf", "text/plain")})
    assert resp.status_code == 400

    listing = client.get("/api/verifications?prediction=error&search=x.txt").json()
    errors = [r for r in listing if r["prediction"] == "error" and r["filename"] == "x.txt"]
    assert errors, "expected an error row for the rejected upload"
    vid = errors[0]["verification_id"]

    audit = client.get(f"/api/verifications/{vid}/audit").json()
    types = [e["event_type"] for e in audit["events"]]
    assert audit_service.EVENT_DOCUMENT_RECEIVED in types
    assert audit_service.EVENT_PIPELINE_FAILED in types
    failure = [e for e in audit["events"] if e["event_type"] == audit_service.EVENT_PIPELINE_FAILED][0]
    assert failure["severity"] == "error"
    assert failure["details"]["phase"] == "processing"


def test_review_action_event(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("audit_review.pdf", _unique_completion_pdf("review"), "application/pdf")},
    )
    assert resp.status_code == 200
    vid = resp.json()["verification_id"]

    fb = client.post(
        f"/api/verifications/{vid}/feedback",
        json={"reviewer_label": "confirmed_genuine", "reviewer_note": "looks fine"},
    )
    assert fb.status_code == 200

    audit = client.get(f"/api/verifications/{vid}/audit").json()
    review = [e for e in audit["events"] if e["event_type"] == audit_service.EVENT_REVIEW_ACTION]
    assert len(review) == 1
    event = review[0]
    assert event["severity"] == "success"
    assert event["status"] == "recorded"
    assert event["details"]["reviewer_label"] == "confirmed_genuine"
    assert event["details"]["is_disagreement"] is False
    assert event["details"]["original_prediction"] == resp.json()["prediction"]
    assert event["details"]["reviewer_note"] == "looks fine"
    # Review action is the last event in the timeline.
    assert audit["events"][-1]["event_type"] == audit_service.EVENT_REVIEW_ACTION


def test_issuer_unavailable_severity_is_warning_and_codes_masked(client):
    resp = client.post(
        "/api/verify",
        files={"file": ("audit_forage.pdf", _forage_style_pdf(), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text[:500]
    vid = resp.json()["verification_id"]
    iv = resp.json().get("issuer_verification") or {}
    assert iv.get("status") == "VERIFICATION_UNAVAILABLE"

    audit = client.get(f"/api/verifications/{vid}/audit").json()
    issuer = [e for e in audit["events"] if e["event_type"] == audit_service.EVENT_ISSUER_ANALYSIS]
    assert issuer
    # Unavailable is a neutral/warning outcome, NEVER red.
    assert issuer[0]["severity"] == "warning"
    assert issuer[0]["details"]["status"] == "VERIFICATION_UNAVAILABLE"
    assert issuer[0]["details"]["checked_identifier_count"] == 2

    # No raw verification codes anywhere in the audit trail payload.
    raw = json.dumps(audit)
    for code in FORAGE_RAW_CODES:
        assert code not in raw, f"raw verification code leaked into audit trail: {code}"