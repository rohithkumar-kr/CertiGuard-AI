# ML Pipeline

## Overview

End-to-end, reproducible pipeline from synthetic data generation to a versioned,
served model. All steps are deterministic via `TRAINING_SEED` (default `42`).

```
src/data/make_dataset.py  ─▶ data/raw/certificates.csv
src/features/build_features.py ─▶ data/processed/features.csv
src/models/train_model.py ─▶ models/artifacts/<version>/ + models/metadata/<version>/
src/models/evaluate_model.py ─▶ per-type metrics + monitoring reports
scripts/run_generalization_validation.py ─▶ frozen external validation
```

## Dataset generation (`src/data/make_dataset.py`)

`DATASET_VERSION = "v4"`. Generates **3,996 rows** across **6 certificate
types** (666 rows each): academic, completion, training, online, technical,
workshop. **1,298 rows are positive (fraudulent).**

- Genuine rows use realistic field patterns and realistic issuers
  (`KNOWN_ISSUERS` + known non-academic/corporate issuers, including workshop
  organizers such as Innovate Academy, QuantumWorks Training, StellarEdge
  Academy, Meridian Skills Institute).
- Fraud rows deliberately violate patterns. Fraud modes include:
  - bad/random certificate IDs (invalid format/checksum)
  - unknown/fake issuers, fake domains
  - impossible issue dates / future dates
  - inconsistent marks (obtained > total) or inconsistent grade bands
  - suspicious keywords and contact URLs
  - missing signature/seal/QR, blank/odd visual profiles
  - workshop-specific modes: `invalid_workshop_code`, `no_event_context`
- Some label noise is injected so the problem is not trivially separable.
- Deterministic `random_state` from `TRAINING_SEED`, reproducible between runs.

## Feature engineering (`src/features/build_features.py`)

Produces the fixed **31-feature** schema (`FEATURE_COLUMNS`), shared with
runtime inference:

`cert_id_format_valid`, `cert_id_checksum_valid`, `issuer_known`,
`issue_year_valid`, `date_consistency_valid`, `candidate_name_present`,
`course_present`, `organization_present`, `text_field_completeness`,
`marks_pattern_valid`, `grade_consistency_valid`, `suspicious_keyword_count`,
`suspicious_url_present`, `signature_present`, `seal_present`, `qr_present`,
`visual_blank_ratio`, `visual_sharpness`, `visual_noise`,
`visual_color_anomaly`, `text_duplicate_similarity`, `issuer_domain_trust`,
`certificate_type_academic`, `certificate_type_completion`,
`certificate_type_training`, `certificate_type_technical`, `recipient_present`,
`completion_date_present`, `issuer_present`, `completion_title_present`,
`certificate_structure_completeness`.

`app/services/feature_service.py` mirrors this exactly at runtime so training
and inference never diverge. Missing values degrade to neutral defaults instead
of failing.

## Training (`src/models/train_model.py`)

- Splits the feature table with `train_test_split(random_state=42)`: v4 uses
  **train 2,596 / validation 600 / test 800** (stratified, no leakage).
- Fits candidate classifiers (Random Forest and Logistic Regression) with
  balanced class weighting, selects the best on the **validation** split.
- Computes train/validation/test metrics (accuracy, precision, recall, F1,
  confusion matrix).
- Persists versioned artifacts + metadata:
  - `models/artifacts/<version>/model.joblib`
  - `models/metadata/<version>/model_metadata.json`
- **Promotion semantics:**
  - default run writes the "active" pointer (promotes);
  - `--no-promote --version <name>` trains a candidate only;
  - `--calibrate {sigmoid|isotonic}` wraps the selected pipeline in
    `CalibratedClassifierCV(cv=3)` fit **on the training split only**; the
    candidate is named `<model>_calibrated_<method>` and never leaks
    validation/test information into calibration.

## Evaluation (`src/models/evaluate_model.py`)

Reports overall and per-certificate-type metrics on the test split, helping to
spot weak strata (e.g., workshop documents before v4).

## Inference layer (unchanged by Phase 8)

Runtime inference (see `docs/architecture.md`) mirrors the training feature
engineering and loads the versioned pipeline. The model version, feature schema
(31 features), decision threshold (0.5), and artifact bytes are **frozen** —
Phase 8 adds an intelligence/consistency/duplicate layer *after* prediction that
never modifies the ML output. No automatic retraining occurs; candidates remain
candidates until an explicit decision.

## OCR in the inference path (Phase 10)

Phase 10 does **not** touch the model, the 31-feature schema, the 0.5
threshold, or the artifact bytes. It only improves the *text feeding the
existing features*:

- Image-heavy / scanned PDFs (tiny or empty text layer) are rendered and
  OCR'd; the recovered text is passed through the exact same
  `extract_fields` → `build_features_from_extraction` → `predict` path.
- OCR text is **not** a new feature. Features such as `candidate_name_present`,
  `completion_date_present`, `issuer_present`, and
  `certificate_structure_completeness` simply see the values they were trained
  to expect, so a previously unreadable genuine certificate no longer scores as
  a missing-structure fraud.
- Extraction quality is reported as *metadata* (`extraction_method`,
  `extraction_confidence`, `completeness`, `ocr_used`, `ocr_failed`) and drives
  a `low_extraction_confidence` advisory signal in the intelligence layer — it
  never enters the feature vector.

## Evidence engine around the model (Phase 12)

Phase 12 leaves the trained pipeline fully intact — same model, same
31-feature schema, same 0.5 threshold, same artifact bytes (SHA-256
`e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337`). It adds a
**deterministic evidence layer around** the ML verdict:

- `app/services/pdf_forensics.py` — PDF structural analysis (launch actions,
  JavaScript, embedded files, encryption, malformed structure).
- `app/services/visual_analysis.py` + `tampering_service.py` — rendered-image
  statistics and tampering detection (JPEG artifacts, ELA, clone detection;
  OpenCV 5.0.0 headless).
- `app/services/qr_service.py` — QR detection, decoding, verification-page
  detection (QR absence is never evidence of fraud).
- `app/services/semantic_service.py` — content-plausibility + OOD checks.
- `app/services/issuer/` — registry-based issuer verification
  (unknown issuer ≠ fake; see `docs/issuer_verification.md`).
- `app/services/anomaly_service.py` — aggregate anomaly engine.
- `app/services/evidence_fusion.py` — deterministic decision tree fusing all
  categories into the final assessment (see `docs/evidence_fusion.md`).

None of these write to the feature vector or alter `prediction`/`risk_score`.
The ML verdict remains exactly as before; the evidence engine provides a
parallel, independently-derived assessment.

## External generalization validation (`scripts/run_generalization_validation.py`)

Runs a **frozen 27-PDF set** (`external_validation/`) through the **real
production pipeline** (validation → extraction → features → prediction), never
the training set:

- 27 documents across academic(6), completion(5), online(4), technical(4),
  training(4), workshop(4).
- Writes `monitoring/generalization_report.json` with overall + per-type
  metrics, false-positive/false-negative lists, and error analysis.
- Supports environment overrides `MODEL_ARTIFACT_DIR`, `MODEL_METADATA_DIR`,
  `GENERALIZATION_REPORT` so candidates can be validated without touching the
  active model (reports: `generalization_report_v4_candidate.json`,
  `generalization_report_v4_calibrated.json`, baseline backups).

## Versioning decision rule

A new model is promoted **only** if it objectively improves required criteria
and does not regress the frozen external set. Phase 6B: `random_forest_v4`
improved the workshop stratum but produced **identical** frozen external results
and identical overall test metrics, so it was **NOT promoted**
(recorded in `monitoring/benchmark_report.json`). Phase 6C: isotonic calibration
improved Brier score with zero prediction changes on the frozen set; the
calibrated model was retained as a candidate, and the production model stayed
`random_forest_v3` at threshold `0.5`. Phase 8 added the review-status layer
on top of the unchanged model — see `docs/architecture.md` for the banding
rules and `backend/tests/test_phase8.py` for their tests.

## Reproduction

```bash
cd backend
python -m src.data.make_dataset
python -m src.features.build_features
python -m src.models.train_model
python -m src.models.evaluate_model
python scripts/run_generalization_validation.py
```