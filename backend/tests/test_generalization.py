"""Tests for the v3 generalization work: model versioning, preserved v1/v2
rollback artifacts, certificate-type inference (including the Phase 5C
technical type), and end-to-end verification of legitimate corporate and
technical certificates."""

from app.core.config import settings
from app.ml import model as model_service
from src.features.build_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION


def test_active_model_is_v3():
    _, _, metadata = model_service.load()
    assert metadata is not None
    assert metadata["model_version"] == "random_forest_v3"
    assert metadata["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert metadata["dataset_version"] == "v3"


def test_v1_artifact_preserved_for_rollback():
    assert (settings.model_artifact_dir / "random_forest_v1" / "model.joblib").exists()
    assert (settings.model_artifact_dir / "random_forest_v1" / "features.json").exists()
    assert (settings.model_metadata_dir / "random_forest_v1" / "model_metadata.json").exists()


def test_v2_artifact_preserved_for_rollback():
    assert (settings.model_artifact_dir / "random_forest_v2" / "model.joblib").exists()
    assert (settings.model_artifact_dir / "random_forest_v2" / "features.json").exists()
    assert (settings.model_metadata_dir / "random_forest_v2" / "model_metadata.json").exists()


def test_model_has_thirty_one_features():
    _, features, _ = model_service.load()
    assert features == FEATURE_COLUMNS
    assert len(features) == 31


def test_completion_certificate_inference(client, completion_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("completion.pdf", completion_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5
    assert body["model_version"] == "random_forest_v3"
    assert body["certificate_type"]["completion"] == 1
    assert body["certificate_type"]["academic"] == 0


def test_completion_certificate_suspicious_variant(client, suspicious_pdf):
    resp = client.post(
        "/api/verify",
        files={"file": ("suspicious.pdf", suspicious_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "suspicious"
    assert body["risk_score"] >= 0.5


def test_technical_certificate_inference(client):
    import pymupdf as fitz

    text = (
        "SecurEdge Labs\nTechnical Certification\n"
        "This is to certify that Ibrahim Suleiman has demonstrated proficiency in "
        "Cybersecurity and is certified by SecurEdge Labs.\n"
        "Certification code : TECH-2024-0881\n"
        "Date of Certification : 11 November 2024\nVerification code embedded"
    )
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(fitz.Rect(72, 72, 540, 720), text, fontsize=11, fontname="helv")
    pdf = bytes(doc.tobytes())
    doc.close()

    resp = client.post(
        "/api/verify",
        files={"file": ("technical.pdf", pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5
    assert body["certificate_type"]["technical"] == 1
    assert body["certificate_type"]["academic"] == 0


def test_aws_certificate_remains_genuine(client, completion_pdf):
    # The AWS-style completion certificate (real-world source in the frozen
    # external set) must stay genuine under v3.
    resp = client.post(
        "/api/verify",
        files={"file": ("completion.pdf", completion_pdf, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] == "genuine"
    assert body["risk_score"] < 0.5