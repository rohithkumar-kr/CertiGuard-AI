# Architecture

## Overview

The system is a two-part application: a FastAPI backend that owns the ML
pipeline and inference, and a React (Vite) single-page frontend. The backend can
serve the built frontend statically, so a production deployment can run on a
single process.

```
Browser (React + Vite SPA)
        │  POST /api/verify (multipart form, field name "file")
        ▼
FastAPI backend (port 8000)
  ├─ app/api/routes.py         HTTP endpoints + request validation
  ├─ app/services/             business logic (verification, extraction, features,
  │                            intelligence, consistency, duplicates, files,
  │                            phase12 evidence pipeline)
  ├─ app/ml/model.py           runtime model loading + prediction wrapper
  ├─ app/database/             SQLAlchemy engine/session + lightweight migrations
  ├─ app/models/               ORM models (Certificate, Verification, Feedback)
  ├─ app/schemas/              Pydantic response schemas
  ├─ app/core/                 config, logging, security (CORS), errors
  └─ app/utils/                file validation, safe paths
```

## Request flow: POST /api/verify

1. **File validation** (`app/utils/file_utils.py`)
   - Extension must be in `ALLOWED_UPLOAD_EXTENSIONS` (pdf/png/jpg/jpeg).
   - Size must be ≤ `MAX_UPLOAD_SIZE_MB` (default 10 MB).
   - Magic bytes must match the declared extension.
   - Exactly one file may be uploaded; multiple files are rejected.
2. **Safe storage** (`app/services/file_service.py`) — randomized stored filename,
   path-traversal-safe join under `UPLOAD_DIR`.
3. **Extraction** (`app/services/extraction_service.py`) — PyMuPDF text extraction
   for PDFs; Pillow/numpy visual features (blank ratio, sharpness, noise, color
   anomaly) for PDFs and images. When a PDF's embedded text layer is insufficient
   (empty, very short, or structurally incomplete) — typical of scanned /
   image-heavy certificates — the pages are rendered and run through the
   centralized OCR layer (`app/services/ocr_service.py`, RapidOCR/ONNX by
   default, Tesseract optional). OCR text is combined with any embedded text
   (`hybrid`) or used alone (`ocr`), then flows through the same field extractors
   as normal text. Returns fields, warnings, visual stats, and Phase 10
   extraction metadata (method, confidence, text length, completeness, OCR use).
4. **Feature building** (`app/services/feature_service.py`) — mirrors
   `src/features/build_features.py` so runtime semantics equal training
   semantics; produces the fixed 31-feature vector. **OCR-recovered text is NOT
   an extra feature** — it only improves the existing text-derived features, so
   the 31-feature schema and the trained pipeline are unchanged.
5. **Prediction** (`app/ml/model.py` + `src/inference/predict.py`) — loads the
   versioned pipeline once (cached), predicts fraud probability, applies the
   `≥ 0.5` decision threshold, computes confidence. **The ML prediction and
   risk score are never modified by later layers.**
6. **Intelligence layer** (`app/services/intelligence_service.py`) — independent
   certificate-type flags (adds online/workshop), structured identity,
   structural signals, quality indicators, and a three-level `review_status`
   (`low_risk` / `manual_review` / `high_risk`) banded from the unchanged risk
   score plus consistency findings. `review_status` is an advisory layer, not a
   model prediction.
7. **Consistency engine** (`app/services/consistency_service.py`) — surfaces
   contradictions (future date, marks > total, grade/marks mismatch, invalid
   certificate ID, unknown issuer, missing expected structure) as findings that
   feed the explanation and review status, never the model features.
8. **Duplicate detection** (`app/services/duplicate_service.py`) — safe
   fingerprints: file content SHA-256, normalized certificate ID, and an
   exact recipient+issuer+course+date identity hash. Reuse is persisted as
   `duplicate_of` / `duplicate_type`.
9. **Persistence** — a `Certificate` row and a `Verification` row (verification
   id, prediction, risk/confidence, model version, extracted info, certificate
   type flags, review status, issuer, fingerprints, duplicate linkage) are
   stored. Phase 10 adds an `extraction_metadata` JSON column with the
   extraction diagnostics for the reviewer workflow.
10. **Response** — prediction, label, risk score, confidence, message, model
    version, certificate type flags, extracted fields, warnings, review status,
    recommended action, intelligence, positive/risk signals, duplicate info,
    and an `extraction` diagnostics block (`method`, `confidence`,
    `confidence_level`, `text_length`, `completeness`, `ocr_used`,
    `ocr_failed`, `ocr_pages`, `fields_detected`, `fields_total`).

Errors surface as user-safe messages via `AppError` handlers; stack traces are
logged server-side and never leaked to clients.

## Verification flow: POST /api/verify

```
UploadFile → validate_file() → save_upload()
  → extract_document() → build_features_from_extraction()
  → model.predict(features) → intelligence + consistency + duplicates
  → persist Certificate + Verification → JSON response
```

## Evidence engine (Phase 12)

After the ML prediction, a deterministic evidence layer
(`app/services/phase12_pipeline.py`) examines the document through independent
categories and fuses them into a final assessment:

```
PDF bytes
 ├─ pdf_forensics   → structural analysis (launch/JS/embedded/encryption)
 ├─ visual_analysis → rendered-image statistics (blank/sharpness/noise/color)
 ├─ tampering       → JPEG artifacts, ELA, clone detection
 ├─ qr              → QR presence, decode, verification-page detection
 ├─ semantic        → content plausibility, OOD checks
 ├─ issuer          → registry lookup, domain consistency, blocklist
 ├─ anomaly         → aggregate anomaly engine
 ├─ external        → external verification (disabled by default)
 └─ duplicate       → file / cert_id / identity reuse
        │
        ▼
 evidence_fusion → final assessment (deterministic decision tree)
```

- Each category runs inside `try/except`; a category failure degrades to
  `UNKNOWN` and never breaks the verification response.
- The fused assessment (`LIKELY_GENUINE` | `LIKELY_SUSPICIOUS` |
  `REQUIRES_VERIFICATION` | `INSUFFICIENT_EVIDENCE`) plus per-category status
  and evidence items is returned in `verification_evidence` and persisted in
  the `evidence_json` column.
- The ML `prediction` / `risk_score` / `review_status` are untouched.
- See `docs/evidence_fusion.md`, `docs/universal_certificate_forensics.md`,
  `docs/tampering_detection.md`, `docs/issuer_verification.md` for the rules
  and guardrails.

## Review status banding

Constants in `intelligence_service.py`: `REVIEW_BAND_MIN = 0.30`,
`HIGH_RISK_THRESHOLD = 0.50`, `MIN_MEDIUM_SIGNALS_FOR_REVIEW = 2`,
`HIGH_SIGNAL_FORCES_REVIEW = True`. Rules:

- `suspicious` prediction → `high_risk`.
- risk ≥ 0.50 → `high_risk`.
- risk ≥ 0.30 → `manual_review`.
- any high-severity risk signal → `manual_review`; ≥ 2 medium signals →
  `manual_review`.
- otherwise `low_risk`.

Recommended actions: `accept` (low_risk), `manual_review`, `investigate`
(high_risk). Thresholds are documented and unit-tested; changing them is a
deliberate, tested act.

## Extraction quality & OCR (Phase 10)

OCR is a best-effort fallback, never a fraud detector:

- `app/services/ocr_service.py` centralizes engine selection (`ocr_enabled`,
  `ocr_engine`: `auto` → RapidOCR → Tesseract, `ocr_languages`, `ocr_dpi`,
  `ocr_max_pages`). RapidOCR bundles its ONNX models so no external Tesseract
  binary is required. Every OCR call fails gracefully and returns a
  structured `OcrResult` instead of raising.
- `extraction_service._text_sufficient()` decides when OCR runs: empty text,
  fewer than `ocr_min_text_chars` (40) characters, or a short layer that
  recovered few core identity fields. Normal text-layer PDFs never touch OCR.
- Extraction metadata is computed for every document: `extraction_method`
  (`pdf_text` | `ocr` | `hybrid` | `none`), `extraction_confidence`
  (text-layer: `0.6 + 0.4 × completeness` capped at 0.95; OCR: mean OCR line
  confidence), `extracted_text_length`, `extraction_completeness` (fraction of
  the 5 core identity fields), `ocr_used`, `ocr_failed`, `ocr_pages`.
- On OCR text, two generic field-recovery fallbacks activate: a standalone
  name line (all-caps / title-case) and a course-title line. They only run on
  OCR-derived text so existing text-layer extraction is unchanged.
- When OCR fails or confidence is low, the intelligence layer adds a
  `low_extraction_confidence` **medium** risk signal:
  *"Low extraction confidence — manual review recommended."* Missing fields
  are treated as an extraction limitation, never as evidence of fraud, and
  extraction quality never feeds the ML features.

## Monitoring flow

- `/api/metrics` aggregates all verification rows: totals, genuine/suspicious/
  error counts, prediction distribution, certificate-type distribution, average
  risk/confidence, model-version usage, **review-status distribution, average
  extraction completeness, issuer distribution, manual-review rate**, and the 10
  most recent records.
- `scripts/check_distribution_change.py` compares the live prediction /
  certificate-type / review-status / issuer / risk-score / extraction
  distributions against a local baseline file
  (`monitoring/distribution_baseline.json`) using Jensen-Shannon distance and
  flags meaningful drift. Fully local, no cloud dependencies.

## Model versioning

- Active artifacts live at `models/artifacts/model.joblib` +
  `models/metadata/model_metadata.json` (symlink-style "current" pointers).
- Every version also has a versioned directory
  `models/artifacts/<version>/model.joblib` and
  `models/metadata/<version>/model_metadata.json`.
- Training promotes only with `python -m src.models.train_model`; candidates
  use `--no-promote`. Metadata records `model_version`, `dataset_version`,
  `feature_schema_version`, seed, split sizes, params, metrics, and the
  `promoted` flag.
- The default loaded version is `random_forest_v3` (see `app/core/config.py`).

## Frontend

React 18 + TypeScript (Vite). Components:

- `UploadCard` — drag/drop + validation (extension/size/empty), blocks verify
  while loading.
- `ProcessingSteps` — animated upload → analysis → result steps.
- `ResultCard` — verdict, risk/confidence, model version, certificate type,
  verification id, warnings, disclaimer, **review-status badge, recommended
  action banner, duplicate note, OOD/priority badges, and Phase 10 extraction
  badges** (extraction method, confidence level, fields detected, OCR
  failure).
- `EvidencePanel` (Phase 12) — the evidence-engine assessment badge plus the
  per-category status grid and evidence items, rendered in the result and in
  the reviewer workbench.
- `ExplanationCard` — positive vs risk signal groups (with severity).
- `MetricsPanel`, `ModelInfo`, `VerificationHistory` (filters + summary),
  `ExtractedInfo` (intelligence identity).

`services/api.ts` centralizes fetch calls; non-2xx responses and network
failures map to user-friendly `ApiError` messages. Duplicate submissions are
prevented by a `verifying` guard plus a disabled button.

## Security notes

- No secrets in code; all runtime settings come from the environment.
- CORS restricted to configured origins (default localhost dev origins).
- Upload paths are traversal-safe; stored filenames are random UUIDs.
- Exception handlers never return stack traces.

## Database schema (SQLite by default; Postgres via DATABASE_URL)

- `certificates` — uploaded file + extracted candidate/org/course + status.
- `verifications` — per-request verdict + `certificate_type` JSON column
  (added by an idempotent lightweight migration for pre-existing DB files),
  plus Phase 8 columns: `review_status`, `issuer`, `issue_date`,
  `file_fingerprint`, `cert_id_fingerprint`, `identity_fingerprint`,
  `duplicate_of`, `duplicate_type`, Phase 9 columns (`ood_status`,
  `review_priority`, `intelligence_json`), and the Phase 10
  `extraction_metadata` column — with indexes on `review_status`, `issuer`,
  `issue_date`, `risk_score`, and the fingerprint columns. All migrations are
  idempotent and created via `database.py` on startup.
- `verification_feedback` — reviewer decisions (Phase 9) plus Phase 11 columns
  `final_assessment`, `anomaly_score`, `anomaly_level`, and the snapshot
  fields used to build labeled datasets (`file_fingerprint`,
  `cert_id_fingerprint`, `identity_fingerprint`, `split`, `dataset_batch`,
  `is_disagreement`).
- The Phase 12 evidence snapshot is stored as `verifications.evidence_json`
  (JSON column) by an idempotent migration, alongside the Phase 11 feedback
  columns on `verification_feedback`.