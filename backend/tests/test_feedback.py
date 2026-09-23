"""Phase 9 tests: feedback model/API, OOD signal, review priority, candidate
dataset, leakage protection, error analysis, and feedback analytics."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import (
    SUSPICIOUS_PDF_TEXT,
    _make_pdf,
)

from src.data.certificate_patterns import checksum_digit

from app.database.database import SessionLocal
from app.models.feedback import VerificationFeedback
from app.models.verification import Verification
from app.services.feedback_service import record_feedback
from app.services.ood_service import compute_ood_status
from app.services.priority_service import compute_review_priority
from src.feedback.candidate_dataset import build_candidate_dataset
from src.feedback.leakage import LeakageError, check_split_leakage
from src.feedback.splitter import assign_splits


def _verify(client, name, content):
    resp = client.post(
        "/api/verify",
        files={"file": (name, content, "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _valid_cert_id(base5: int) -> str:
    """Build a CERT-2021-<6 digits> id that passes the format checksum."""
    base = f"{base5:05d}"
    return f"CERT-2021-{base}{checksum_digit(base)}"


def _unique_cert_text(name: str, cert_id: str) -> str:
    return (
        "University of Cambridge\n"
        "Certificate of Achievement\n"
        "\n"
        f"We hereby certify that {name} has completed the Computer Science program.\n"
        "\n"
        "Program offered by University of Cambridge\n"
        f"Candidate ID: {cert_id}\n"
        "Marks: 95 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2021-06-15\n"
        "Signature: ____________________\n"
        "Seal: University Seal\n"
        "QR code available for verification\n"
    )


def _clear_feedback(db_session) -> None:
    """Clear feedback rows so candidate-dataset tests are deterministic in the
    shared test database."""
    db_session.query(VerificationFeedback).delete()
    db_session.commit()


def _make_unique_genuine_pdf(name: str, cert_id: str) -> bytes:
    return _make_pdf(_unique_cert_text(name, cert_id) + f"\nUnique marker: {name}\n")


def _make_unique_suspicious_pdf(marker: str) -> bytes:
    text = (
        "Online Degree Emporium\n"
        "Instant Certificate\n"
        "\n"
        "Buy verified certificates online, no exam needed.\n"
        f"Unique marker: {marker}\n"
        f"Candidate ID: FREECERT-2022-{marker}\n"
        "Marks: 150 out of 100\n"
        "Grade: A\n"
        "Issue Date: 2026-12-01\n"
    )
    return _make_pdf(text)


# Unique genuine variants: unique recipient name + valid cert ID + unique
# content, so no fingerprint overlaps with the shared genuine_pdf fixture that
# test_phase8 expects to be its first (non-duplicate) upload.
import itertools as _itertools

_GENUINE_VARIANTS = _itertools.count(1001)
_SUSPICIOUS_VARIANTS = _itertools.count(2001)


def _genuine_variant() -> bytes:
    n = next(_GENUINE_VARIANTS)
    return _make_unique_genuine_pdf(
        f"Variant User {n}", _valid_cert_id(10000 + n)
    )


def _suspicious_variant() -> bytes:
    n = next(_SUSPICIOUS_VARIANTS)
    return _make_pdf(SUSPICIOUS_PDF_TEXT + f"\nUnique marker: feedback-s{n}\n")


# ---------------------------------------------------------------------------
# 9A/9B: feedback recording
# ---------------------------------------------------------------------------

def test_valid_feedback(client, db_session):
    body = _verify(client, "fb_valid.pdf", _genuine_variant())
    resp = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine", "reviewer_note": "Matches records"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["reviewer_label"] == "confirmed_genuine"
    assert data["reviewer_note"] == "Matches records"
    assert data["original_prediction"] == body["prediction"]
    assert data["original_risk_score"] == body["risk_score"]
    assert data["reviewed_at"] is not None

    row = (
        db_session.query(VerificationFeedback)
        .filter(VerificationFeedback.verification_id == body["verification_id"])
        .one()
    )
    assert row.reviewer_label == "confirmed_genuine"
    assert row.original_prediction == "genuine"
    assert row.is_disagreement is False


def test_feedback_validation_invalid_label(client):
    body = _verify(client, "fb_badlabel.pdf", _genuine_variant())
    resp = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "definitely_fake"},
    )
    assert resp.status_code == 422
    errors = resp.json()["detail"]
    assert any("reviewer_label" in str(e.get("loc")) for e in errors)


def test_feedback_validation_missing_verification(client):
    resp = client.post(
        "/api/verifications/V-NOPE-0000/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_feedback_validation_note_too_long(client):
    body = _verify(client, "fb_longnote.pdf", _genuine_variant())
    resp = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine", "reviewer_note": "x" * 3000},
    )
    assert resp.status_code == 422


def test_duplicate_feedback_rejected(client):
    body = _verify(client, "fb_dup.pdf", _genuine_variant())
    first = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )
    assert second.status_code == 400
    assert "already been reviewed" in second.json()["detail"]


def test_uncertain_feedback(client, db_session):
    body = _verify(client, "fb_uncertain.pdf", _genuine_variant())
    resp = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "uncertain"},
    )
    assert resp.status_code == 200
    assert resp.json()["reviewer_label"] == "uncertain"
    row = (
        db_session.query(VerificationFeedback)
        .filter(VerificationFeedback.verification_id == body["verification_id"])
        .one()
    )
    assert row.is_disagreement is False


def test_feedback_never_changes_prediction(client):
    body = _verify(client, "fb_nochange.pdf", _genuine_variant())
    original_prediction = body["prediction"]
    original_risk = body["risk_score"]
    client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )
    # The verification record is unchanged by feedback.
    detail = client.get(f"/api/verifications/{body['verification_id']}").json()
    assert detail["prediction"] == original_prediction
    assert detail["risk_score"] == original_risk


# ---------------------------------------------------------------------------
# 9B: feedback summary + 9I: analytics
# ---------------------------------------------------------------------------

def test_feedback_summary_counts(client):
    before = client.get("/api/feedback/summary").json()
    g = _verify(client, "fb_sum_g.pdf", _genuine_variant())
    s = _verify(client, "fb_sum_s.pdf", _suspicious_variant())
    client.post(
        f"/api/verifications/{g['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    client.post(
        f"/api/verifications/{s['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )
    after = client.get("/api/feedback/summary").json()
    # Both reviews agree with the AI, so deltas are exact regardless of
    # shared test-DB state accumulated by earlier tests.
    assert after["confirmed_genuine"] == before["confirmed_genuine"] + 1
    assert after["confirmed_suspicious"] == before["confirmed_suspicious"] + 1
    assert after["total_reviewed"] == before["total_reviewed"] + 2
    assert after["disagreement_count"] == before["disagreement_count"]
    assert after["agreement_count"] == before["agreement_count"] + 2


def test_feedback_disagreement_tracking(client):
    before = client.get("/api/feedback/summary").json()
    body = _verify(client, "fb_disagree.pdf", _genuine_variant())
    assert body["prediction"] == "genuine"
    resp = client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_disagreement"] is True
    after = client.get("/api/feedback/summary").json()
    assert after["disagreement_count"] == before["disagreement_count"] + 1


def test_feedback_analytics_insufficient_samples(db_session):
    from app.services.feedback_service import _aggregate

    # A single decisive review is far below the 10-sample minimum.
    block = _aggregate([])
    assert block["sufficient"] is False
    # Percentages must not be invented for tiny samples.
    assert "false_positive_rate" not in block
    assert "accuracy" not in block


def test_feedback_analytics_structure(client):
    analytics = client.get("/api/feedback/analytics").json()
    for key in (
        "summary", "overall", "by_certificate_type", "by_issuer",
        "by_review_status", "by_priority", "by_extraction_completeness",
        "average_extraction_completeness", "ood_distribution",
        "review_priority_distribution", "manual_review_rate",
    ):
        assert key in analytics


# ---------------------------------------------------------------------------
# 9F: OOD signal
# ---------------------------------------------------------------------------

def test_ood_status_present_in_response(client):
    g = _verify(client, "ood_g.pdf", _genuine_variant())
    s = _verify(client, "ood_s.pdf", _suspicious_variant())
    assert g["ood_status"] in ("normal", "unusual", "insufficient_information")
    assert s["ood_status"] in ("normal", "unusual", "insufficient_information")
    # Genuine Cambridge certificate should be normal.
    assert g["ood_status"] == "normal"


def test_ood_status_pure():
    extraction = type("X", (), {"fields": {}, "text": ""})()
    # No text + no fields -> insufficient_information
    assert compute_ood_status({}, extraction, {}) == "insufficient_information"

    class F(dict):
        pass

    extraction = type("X", (), {
        "fields": {
            "candidate_name": "A", "organization": "University of Cambridge",
            "course": "CS", "issue_date": "2022-01-01", "cert_id": "CERT-2022-123456",
        },
        "text": "University of Cambridge Certificate",
    })()
    intel = {
        "certificate_type": {"flags": {"academic": 1, "online": 0, "workshop": 0},
                             "primary": "academic"},
        "structure_completeness": 1.0,
        "issuer_status": "ok",
        "quality_indicators": {"blank_document": False, "color_anomaly": False, "text_present": True},
        "consistency_findings": [],
    }
    features = {"suspicious_keyword_count": 0, "suspicious_url_present": 0}
    assert compute_ood_status(intel, extraction, features) == "normal"

    # Academic + online combination is unusual.
    intel["certificate_type"] = {"flags": {"academic": 1, "online": 1, "workshop": 0},
                                 "primary": "academic"}
    assert compute_ood_status(intel, extraction, features) == "unusual"


def test_ood_status_never_proof_of_fraud(client):
    body = _verify(client, "ood_fraud.pdf", _suspicious_variant())
    assert body["prediction"] == "suspicious"
    # OOD is advisory; it must be present but never equal to a fraud verdict.
    assert body["ood_status"] in ("normal", "unusual", "insufficient_information")


# ---------------------------------------------------------------------------
# 9G: review priority
# ---------------------------------------------------------------------------

def test_review_priority_rules_pure():
    assert compute_review_priority(0.1, "low_risk", [], {}, "normal", 1.0, 1.0) == "low"
    assert compute_review_priority(0.1, "low_risk", [], {"is_duplicate": True}, "normal", 1.0, 1.0) == "high"
    assert compute_review_priority(0.9, "high_risk", [], {}, "normal", 1.0, 1.0) == "high"
    assert compute_review_priority(0.1, "low_risk", [{"key": "invalid_date", "severity": "high"}], {}, "normal", 1.0, 1.0) == "high"
    assert compute_review_priority(0.1, "low_risk", [], {}, "unusual", 1.0, 1.0) == "high"
    assert compute_review_priority(0.35, "manual_review", [], {}, "normal", 1.0, 1.0) == "medium"
    assert compute_review_priority(0.1, "low_risk", [], {}, "insufficient_information", 1.0, 1.0) == "medium"


def test_review_priority_persisted(client):
    g = _verify(client, "prio_g.pdf", _genuine_variant())
    s = _verify(client, "prio_s.pdf", _suspicious_variant())
    assert g["review_priority"] in ("low", "medium", "high")
    assert s["review_priority"] in ("low", "medium", "high")


def test_review_priority_does_not_alter_prediction(client):
    body = _verify(client, "prio_nochange.pdf", _suspicious_variant())
    assert body["prediction"] == "suspicious"
    assert body["review_priority"] == "high"


# ---------------------------------------------------------------------------
# 9C/9E: error analysis + quality report
# ---------------------------------------------------------------------------

def test_error_analysis_insufficient_samples(db_session):
    from src.feedback.analyze import analyze_feedback, _metrics

    rows = []
    block = _metrics(rows, min_samples=10)
    assert block["sufficient"] is False
    assert block["note"] == "insufficient samples"

    # A synthetic minimal set with exactly enough samples.
    class R:
        def __init__(self, truth, pred):
            self.reviewer_label = truth
            self.original_prediction = pred
            self.is_disagreement = truth == "confirmed_suspicious" and pred != "suspicious"

    fake_rows = [R("confirmed_genuine", "genuine") for _ in range(6)] + \
                [R("confirmed_suspicious", "suspicious") for _ in range(6)]
    block = _metrics(fake_rows, min_samples=10)
    assert block["sufficient"] is True
    assert block["confusion_matrix"]["tp"] == 6
    assert block["confusion_matrix"]["tn"] == 6
    assert block["accuracy"] == 1.0


def test_quality_report_underrepresented(tmp_path):
    from src.feedback.quality_report import build_quality_report

    rows = []
    for i in range(12):
        rows.append({
            "reviewer_label": "confirmed_genuine" if i % 2 == 0 else "confirmed_suspicious",
            "label": 0 if i % 2 == 0 else 1,
            "certificate_type": "academic",
            "issuer": "University of Cambridge",
            "extraction_completeness": 0.8,
            "is_disagreement": 0,
            "file_fingerprint": f"fp{i}",
            "cert_id_fingerprint": f"cid{i}",
            "identity_fingerprint": f"id{i}",
            "certificate_id": f"CERT-2021-{i:06d}",
            "split": "train" if i < 10 else "test",
            "candidate_name": f"Name {i}", "organization": "University of Cambridge",
            "course": "CS", "issue_date": "2022-01-01", "cert_id": f"CERT-2021-{i:06d}",
        })
    df = pd.DataFrame(rows)
    report = build_quality_report(df)
    assert report["class_balance"] == {"genuine": 6, "suspicious": 6}
    assert report["rebalanced"] is False
    assert "certificate_types" in report["underrepresented_categories"]
    assert report["possible_leakage_cross_split"]["certificate_id"] == 0


# ---------------------------------------------------------------------------
# 9D/9K: candidate dataset + leakage
# ---------------------------------------------------------------------------

def test_candidate_dataset_build(tmp_path, client, db_session):
    _clear_feedback(db_session)
    g = _verify(client, "cd_genuine.pdf", _make_unique_genuine_pdf("Cameron Builder", _valid_cert_id(90000)))
    s = _verify(client, "cd_suspicious.pdf", _make_unique_suspicious_pdf("CDBUILD"))
    assert g["prediction"] == "genuine"
    assert s["prediction"] == "suspicious"
    client.post(
        f"/api/verifications/{g['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    client.post(
        f"/api/verifications/{s['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )

    db = SessionLocal()
    try:
        report = build_candidate_dataset(
            db, tmp_path, test_fraction=0.5, seed=42,
            external_dir=None,
        )
    finally:
        db.close()

    assert report["rows_written"] == 2
    assert report["class_balance"] == {"confirmed_genuine": 1, "confirmed_suspicious": 1}
    csv_path = Path(report["candidate_dataset"])
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    assert set(df["split"]) <= {"train", "test"}
    assert df["reviewer_label"].isin(["confirmed_genuine", "confirmed_suspicious"]).all()
    # Feature vector present for the 31-feature schema.
    from src.features.build_features import FEATURE_COLUMNS
    assert all(col in df.columns for col in FEATURE_COLUMNS)
    assert len(df.columns) >= len(FEATURE_COLUMNS) + 12
    # Leakage must pass (splitter keeps families together).
    assert report["leakage"]["split"]["ok"] is True


def test_candidate_dataset_excludes_uncertain(tmp_path, client, db_session):
    _clear_feedback(db_session)
    g = _verify(client, "cd_ex_g.pdf", _make_unique_genuine_pdf("Emma Examiner", _valid_cert_id(90001)))
    s = _verify(client, "cd_ex_s.pdf", _make_unique_suspicious_pdf("CDEXCL"))
    client.post(
        f"/api/verifications/{g['verification_id']}/feedback",
        json={"reviewer_label": "uncertain"},
    )
    client.post(
        f"/api/verifications/{s['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_suspicious"},
    )
    db = SessionLocal()
    try:
        report = build_candidate_dataset(db, tmp_path, external_dir=None)
    finally:
        db.close()
    # Uncertain row excluded; only the confirmed_suspicious row qualifies.
    assert report["rows_written"] == 1
    assert report["class_balance"] == {"confirmed_genuine": 0, "confirmed_suspicious": 1}


def test_candidate_dataset_duplicate_prevention(tmp_path, client, db_session):
    _clear_feedback(db_session)
    content = _make_pdf(_unique_cert_text("Dup Reviewer", _valid_cert_id(90002)) + "\nUnique marker: cd-dup\n")
    a = _verify(client, "cd_dup_a.pdf", content)
    b = _verify(client, "cd_dup_b.pdf", content)
    assert b["duplicate"]["is_duplicate"] is True  # same file fingerprint
    client.post(
        f"/api/verifications/{a['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    client.post(
        f"/api/verifications/{b['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    db = SessionLocal()
    try:
        report = build_candidate_dataset(db, tmp_path, external_dir=None)
    finally:
        db.close()
    assert report["duplicate_rows_removed"] >= 1
    assert report["rows_written"] == 1


def test_leakage_detection_fails_loudly():
    df = pd.DataFrame({
        "certificate_id": ["CERT-2021-000001", "CERT-2021-000001"],
        "file_fingerprint": ["abc", "abc"],
        "cert_id_fingerprint": ["x", "x"],
        "identity_fingerprint": ["y", "y"],
        "split": ["train", "test"],
    })
    with pytest.raises(LeakageError):
        check_split_leakage(df)


def test_splitter_keeps_families_together():
    df = pd.DataFrame({
        "certificate_id": ["CERT-2021-000001", "CERT-2021-000001"],
        "file_fingerprint": ["a", "a"],
        "cert_id_fingerprint": ["x", "x"],
        "identity_fingerprint": ["y", "y"],
        "label": [0, 1],
    })
    out = assign_splits(df, test_fraction=0.5, seed=42)
    assert len(set(out["split"])) == 1  # both rows must share one split
    check_split_leakage(out)  # must not raise


def test_external_validation_leakage_check(tmp_path, genuine_pdf):
    from src.feedback.leakage import check_external_validation_leakage
    from app.services.duplicate_service import file_fingerprint

    ext = tmp_path / "external"
    ext.mkdir()
    (ext / "doc.pdf").write_bytes(genuine_pdf)
    df = pd.DataFrame({"file_fingerprint": [file_fingerprint(genuine_pdf), "none"]})
    with pytest.raises(LeakageError):
        check_external_validation_leakage(df, ext)


# ---------------------------------------------------------------------------
# 9H: verification detail endpoint
# ---------------------------------------------------------------------------

def test_verification_detail_endpoint(client):
    body = _verify(client, "detail.pdf", _genuine_variant())
    detail = client.get(f"/api/verifications/{body['verification_id']}").json()
    assert detail["prediction"] == body["prediction"]
    assert detail["risk_score"] == body["risk_score"]
    assert detail["ood_status"] == body["ood_status"]
    assert detail["review_priority"] == body["review_priority"]
    assert "positive_signals" in detail
    assert "risk_signals" in detail
    assert "consistency_findings" in detail["intelligence"]
    assert "duplicate" in detail


def test_verification_detail_not_found(client):
    resp = client.get("/api/verifications/V-NOPE-0000")
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_history_includes_feedback_fields(client):
    body = _verify(client, "hist_fb.pdf", _genuine_variant())
    client.post(
        f"/api/verifications/{body['verification_id']}/feedback",
        json={"reviewer_label": "confirmed_genuine"},
    )
    rows = client.get("/api/verifications?limit=100").json()
    row = next(r for r in rows if r["verification_id"] == body["verification_id"])
    assert row["reviewer_label"] == "confirmed_genuine"
    assert row["reviewed_at"] is not None


# ---------------------------------------------------------------------------
# 9L: existing Phase 8 behavior preserved
# ---------------------------------------------------------------------------

def test_phase8_review_status_still_works(client):
    body = _verify(client, "p8_review.pdf", _suspicious_variant())
    assert body["prediction"] == "suspicious"
    assert body["review_status"] == "high_risk"
    assert body["recommended_action"]["action"] == "investigate"


def test_phase8_duplicate_still_works(client):
    content = _make_pdf(_unique_cert_text("P8 Duplicate", _valid_cert_id(90003)) + "\nUnique marker: p8-dup\n")
    _verify(client, "p8_dup1.pdf", content)
    second = _verify(client, "p8_dup2.pdf", content)
    assert second["duplicate"]["is_duplicate"] is True
    assert second["duplicate"]["duplicate_type"] == "file"