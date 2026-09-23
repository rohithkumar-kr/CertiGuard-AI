# AI-Powered Certificate Verification & Fraud Detection

> **AI-based preliminary fraud-risk assessment** for educational and professional
> certificates. The system predicts whether a certificate is **likely genuine** or
> **suspicious** using extracted fields, document structure, and a trained ML model.

---

## 1. Overview

Forged and tampered certificates are a growing problem for employers, admissions
offices, and institutions. This project builds an automated **preliminary
screening** step that flags documents as likely genuine or suspicious before any
manual review, using a FastAPI backend, a scikit-learn ML pipeline, and a React
frontend.

## 2. Important Model Claim

> **This system performs an AI-based PRELIMINARY fraud-risk assessment. It is NOT
> a legal or institutional authentication service, and it does NOT guarantee
> document authenticity.**

- Predictions are **probabilistic risk scores** from a model trained on
  **synthetic/prototype data**.
- Unusual or out-of-distribution certificate formats **can still produce false
  positives** (a genuine document incorrectly flagged as suspicious) and false
  negatives (a fraudulent document missed).
- Always combine results with **manual review** for high-stakes decisions
  (hiring, admissions, licensing).

## 3. Features

- Upload a certificate (PDF, PNG, JPG/JPEG; max 10 MB) with strict file
  validation (extension, magic bytes, size) and concurrent-burst protection.
- Extract text (PDFs), visual signals (blank ratio, sharpness, noise, color
  anomaly), and structured fields (candidate, issuer, course, dates, marks,
  grade).
- Detect certificate type: **academic, completion, training, online, technical,
  workshop**.
- Run a trained Random Forest classifier producing `prediction`, `risk_score`,
  and `confidence`, plus a human-readable **explanation** of detected signals.
- Persist every verification with the model version used; expose searchable,
  filterable, sortable history and aggregate metrics.
- **Monitoring** endpoint with genuine/suspicious/error counts, average risk,
  model version usage, and certificate-type distribution, plus a local
  distribution-change (drift) detection script.
- **Workflow UI** (upload → processing → AI analysis → result), result
  explanation, manual-review guidance for suspicious results, and a monitoring
  dashboard with certificate-type breakdown.
- **Certificate intelligence layer** (Phase 8): structured certificate type,
  extracted identity, structural signals (signature/seal/QR/URL), document
  quality indicators, and a consistency engine that surfaces contradictions
  (future date, marks > total, grade/marks mismatch, invalid certificate ID,
  unknown issuer, missing expected structure) — missing fields are reported as
  missing, never as fraud.
- **Risk explanation engine**: positive trust signals vs risk signals, with
  wording like "detected risk signal" / "requires manual review" (never
  "proves fraud").
- **Three-level review status**: `low_risk`, `manual_review`, `high_risk`
  layered on the unchanged ML prediction (threshold stays 0.5).
- **Duplicate / reuse detection** via safe fingerprints: exact file content,
  certificate ID, and recipient+issuer+course+date. Two different legitimate
  certificates of the same person are not flagged.
- **Advanced history**: filter/sort by prediction, review status, certificate
  type, issuer, date range, and risk range, plus a summary
  (total / genuine / suspicious / manual review / average risk).
- **Extended monitoring**: prediction, certificate-type, and review-status
  distributions, average extraction completeness, issuer distribution, and
  manual-review rate, all fully local.
- **Human review feedback loop** (Phase 9): reviewers can confirm genuine /
  confirm suspicious / mark uncertain per verification. Feedback never changes
  the ML prediction or risk score — it is stored as immutable evidence.
- **Out-of-distribution signal** (`ood_status`): advisory `normal` / `unusual` /
  `insufficient_information` indicator, computed outside the ML features and
  never treated as proof of fraud.
- **Review prioritization** (`review_priority`): `low` / `medium` / `high`
  triage for human review, separate from the prediction and review status.
- **Feedback analytics**: agreement/disagreement rates, reviewer-vs-model
  confusion metrics (reported only when sample counts are sufficient),
  per-type/issuer/priority breakdowns, and extraction-completeness buckets.
- **Candidate dataset + leakage protection** (Phase 9K): build a leakage-safe
  train/test candidate CSV from confirmed reviews; duplicate samples are
  deduplicated and leakage fails loudly instead of being silently promoted.
- **Review Workbench UI**: browse review-priority-ordered verifications with
  full signals, submit a decision, and view feedback analytics.
- **Robust extraction + OCR fallback** (Phase 10): image-heavy / scanned
  certificates (empty or tiny text layer) are rendered and OCR'd
  (RapidOCR/ONNX, no external binary). Recovered fields flow through the same
  fixed 31-feature pipeline — OCR is not a feature and never changes the
  model. Every verification reports extraction diagnostics (method, confidence,
  completeness, OCR use/failure); low-confidence or failed extraction triggers
  *"Low extraction confidence — manual review recommended"* instead of treating
  missing fields as fraud.
- **Universal certificate evidence engine** (Phase 12): a deterministic
  multi-layer evidence layer runs alongside the ML verdict. PDF forensics
  (launch actions / JavaScript / embedded files / encryption), rendered-image
  tampering detection (JPEG artifacts, error-level analysis, clone detection),
  QR analysis (presence never proves authenticity), semantic/OOD checks,
  registry-based issuer verification (unknown issuer ≠ fake), an aggregate
  anomaly engine, and duplicate-reuse evidence are fused by a transparent
  decision tree into `LIKELY_GENUINE` / `LIKELY_SUSPICIOUS` /
  `REQUIRES_VERIFICATION` / `INSUFFICIENT_EVIDENCE` with per-category evidence
  surfaced in the UI. The model, 31 features, and 0.5 threshold are untouched;
  evidence rules never treat missing fields, image-only docs, OCR failure, or
  unknown issuers as fraud.
- Centralized configuration (`.env`), structured operational logging, hardened
  error responses (no internal detail leaks), and a consistent JSON error model.

## 4. Architecture

```
Browser (React + Vite SPA)
        │  POST /api/verify (multipart file)
        ▼
FastAPI backend
  ├─ file validation + safe storage      app/services, app/utils
  ├─ text/visual extraction              app/services/extraction_service.py
  ├─ feature building (31 features)      app/services/feature_service.py
  ├─ ML prediction                       app/ml/model.py + src/inference/predict.py
  ├─ intelligence + consistency          app/services/intelligence_service.py
  │                                      app/services/consistency_service.py
  ├─ duplicate detection                 app/services/duplicate_service.py
  ├─ OOD + review priority               app/services/ood_service.py
  │                                      app/services/priority_service.py
  ├─ evidence engine (Phase 12)          app/services/phase12_pipeline.py
  │                                      app/services/pdf_forensics.py
  │                                      app/services/visual_analysis.py
  │                                      app/services/tampering_service.py
  │                                      app/services/qr_service.py
  │                                      app/services/semantic_service.py
  │                                      app/services/anomaly_service.py
  │                                      app/services/evidence_fusion.py
  │                                      app/services/issuer/
  ├─ feedback recording + analytics      app/services/feedback_service.py
  ├─ persistence                         SQLAlchemy + SQLite
  └─ monitoring                          app/api/routes.py + scripts/ + monitoring/
```

Feedback / learning pipeline (offline):

```
app/services/feedback_service.py  → reviewer decisions (immutable)
src/feedback/candidate_dataset.py → data/reviewed/*.csv   (leakage-safe candidates)
src/feedback/analyze.py           → reviewer-vs-model error analysis
src/feedback/quality_report.py    → candidate dataset quality report
src/feedback/benchmark.py         → candidate model comparison (never promotes)
```

Training pipeline (offline):

```
src/data/make_dataset.py   →  data/raw/certificates.csv  (synthetic, reproducible)
src/features/build_features.py → data/processed/features.csv
src/models/train_model.py   →  models/artifacts/ + models/metadata/  (versioned)
```

The active production model is `random_forest_v3` (31 features). Candidates are
trained with `--no-promote` and never overwrite the active artifacts.

## 5. Tech Stack

- **Backend:** Python, FastAPI, Uvicorn, SQLAlchemy (SQLite), python-multipart,
  pydantic, PyMuPDF (text), Pillow/numpy (visuals), RapidOCR + onnxruntime (OCR,
  bundled ONNX models — no external Tesseract binary required)
- **ML:** scikit-learn (Random Forest, Logistic Regression), joblib, numpy, pandas
- **Frontend:** React 18 + Vite + TypeScript
- **Testing:** pytest + FastAPI TestClient

## 6. Repository Structure

```
AI-Certificate-Verification/
  backend/
    app/            FastAPI application (api, core, database, models, schemas, services, ml)
    src/            ML pipeline (data, features, models, inference)
    src/feedback/   feedback/label, leakage, splitter, candidate dataset, error analysis, benchmark
    data/raw        synthetic dataset (v4: 3996 rows, 6 certificate types)
    data/processed  engineered features
    data/reviewed   candidate datasets built from confirmed human reviews
    models/         versioned artifacts + metadata
    monitoring/     benchmark/generalization/distribution reports, logs
    scripts/        run scripts, validation, drift detection, feedback analysis
    tests/          pytest suite (206 tests)
    external_validation/  frozen 27-PDF held-out validation set
  frontend/         React + Vite SPA (incl. Review Workbench)
  docs/             architecture.md, ml_pipeline.md, model_evaluation.md, api.md, DEPLOYMENT.md, feedback_learning.md, extraction_pipeline.md
```

## 7. Dataset

There is **no public dataset** of real labeled certificates, so the project uses
a **synthetic, reproducible dataset**:

- `backend/src/data/make_dataset.py` generates **v4**: 6 certificate types
  (academic, completion, training, online, technical, workshop) × 666 =
  **3,996 rows** (1,298 positive / fraudulent).
- Deterministic seed `42` (env `TRAINING_SEED`).
- Genuine rows follow realistic field patterns; fraudulent rows deliberately
  violate them (bad IDs, unknown issuers, inconsistent marks, suspicious
  keywords, missing seals/signatures, workshop fraud modes, etc.), with some
  label noise.
- **All data is synthetic — no real certificates or personal data are used.**

## 8. ML Pipeline

1. `python -m src.data.make_dataset` → raw CSV
2. `python -m src.features.build_features` → 31-feature table
3. `python -m src.models.train_model` → train/val/test split (no leakage,
   `random_state=42`), fits Random Forest + Logistic Regression, selects the
   best on validation, persists versioned artifacts + metadata
4. `python -m src.models.evaluate_model` → metrics + per-type analysis
5. `python -m scripts.run_generalization_validation` → frozen 27-PDF held-out
   external validation through the **real production pipeline**

Model versioning:

```bash
python -m src.models.train_model                       # train + promote
python -m src.models.train_model --no-promote --version random_forest_vX   # candidate
python -m src.models.train_model --calibrate isotonic --no-promote ...     # calibrated candidate
```

Calibration (if used) is fit on the **training split only** via
`CalibratedClassifierCV`, never on validation or the frozen set.

## 9. Model Evaluation

Active model: **random_forest_v3**, 31 features.

Held-out test split (v3 own split, 800 rows):

| Metric | Value |
|---|---|
| Accuracy | 0.9287 |
| Precision | 0.9422 |
| Recall | 0.8281 |
| F1 | 0.8815 |

Frozen external validation — 27 PDFs, never seen in training, run through the
real pipeline:

| Metric | Value |
|---|---|
| Accuracy | 0.963 |
| Genuine recall | 0.9286 |
| Suspicious recall | 1.0000 |
| False positives | 1 |
| False negatives | 0 |

The single false positive is `academic/deshpande_501766.pdf`, an internally
inconsistent genuine certificate (grade "B" vs 91/100) — an expected
false-positive pattern for an AI screening tool. Full per-type metrics and
decision records live in `backend/monitoring/` and `docs/model_evaluation.md`.

## 10. API

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | status, app name, model version/loaded |
| GET | `/api/model/info` | model version, name, feature list, metrics |
| POST | `/api/verify` | upload one certificate (PDF/PNG/JPG), returns verdict + intelligence |
| GET | `/api/verifications?limit=N` | recent verifications (1–100); supports `search`, `prediction`, `review_status`, `certificate_type`, `issuer`, `date_from`/`date_to`, `risk_min`/`risk_max`, `sort` |
| GET | `/api/verifications/summary` | summary counts over history (respects the same filters) |
| GET | `/api/metrics` | totals, genuine/suspicious/error counts, avg risk, cert-type/review-status/issuer distributions, extraction completeness, manual-review rate |
| GET | `/api/verifications/{id}` | full detail for one verification (reviewer workflow) |
| POST | `/api/verifications/{id}/feedback` | record a human review decision (confirmed_genuine / confirmed_suspicious / uncertain) |
| GET | `/api/feedback/summary` | feedback counts: reviewed, per label, agreement/disagreement rates |
| GET | `/api/feedback/analytics` | reviewer-vs-model metrics with sample-size guards |

Errors: 400 invalid file, 422 malformed request, 503 model unavailable, 500
unexpected. Multiple uploads to `/api/verify` are rejected, and concurrent
verifications are bounded. Responses follow a consistent `{"detail": ...}`
JSON error model with no internal traceback leakage. See `docs/api.md`.

## 11. Setup & Installation

Requirements: Python 3.13, Node.js 18+.

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate            # Windows  |  source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # Windows  |  cp .env.example .env

# Frontend
cd ../frontend
npm install
```

Environment variables (see `backend/.env.example`): `DATABASE_URL`,
`MODEL_VERSION`, `MODEL_ARTIFACT_DIR`, `MODEL_METADATA_DIR`,
`MAX_UPLOAD_SIZE_MB`, `ALLOWED_UPLOAD_EXTENSIONS`, `CORS_ORIGINS`,
`TRAINING_SEED`, `BACKEND_HOST`, `BACKEND_PORT`, `APP_ENV`, `LOG_LEVEL`,
`UPLOAD_RETENTION_MAX`, `MAX_CONCURRENT_VERIFICATIONS`, `DECISION_THRESHOLD`,
and the OCR settings (`OCR_ENABLED`, `OCR_ENGINE`, `OCR_DPI`,
`OCR_MAX_PAGES`, `OCR_MIN_TEXT_CHARS`, `OCR_HYBRID_CHARS`,
`OCR_MIN_COMPLETENESS`, `OCR_LANGUAGES` — see `docs/extraction_pipeline.md`).
For production deployment see `docs/DEPLOYMENT.md`.

## 12. Usage

```bash
# Train (first run only; artifacts are already included)
cd backend
python -m src.training.run_pipeline

# Run backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run frontend (dev, proxies /api to backend)
cd frontend
npm run dev
```

Open `http://localhost:5173` and upload a certificate.

## 13. Testing, Monitoring & Limitations

**Testing:** 259 pytest tests — preprocessing, features, model, API success/error
paths, file validation, upload retention, DB idempotency/indexes, generalization,
dataset reproducibility, Phase 8 certificate intelligence, review status,
duplicate detection, history filters, and summary, plus Phase 9 feedback
recording/validation, agreement & disagreement tracking, OOD signal, review
priority, verification detail, candidate dataset generation (dedupe + leakage),
error analysis, quality report, analytics sample-size guards, and Phase 10
extraction/OCR tests (text sufficiency, OCR fallback, hybrid, graceful OCR
failure, extraction metadata, and model invariants), plus Phase 12 evidence
engine tests (evidence unit tests, model-integrity invariants, and the
known-difficult regression set).

```bash
cd backend
python -m pytest tests -q
```

**Monitoring & feedback analysis:**

```bash
# Live metrics via API
curl http://localhost:8000/api/metrics

# Distribution-change (drift) detection, local-only
python scripts/check_distribution_change.py --update-baseline   # snapshot baseline
python scripts/check_distribution_change.py                     # compare + report

# Feedback / learning loop tooling (offline, never auto-promotes)
python scripts/analyze_feedback.py              # reviewer-vs-model error analysis
python scripts/data_quality_report.py           # candidate dataset quality report
python scripts/build_candidate_dataset.py       # leakage-safe candidate CSV
python scripts/benchmark_reviewed_models.py     # compare candidates (no promotion)

# Phase 12 evidence-engine validation (dedicated DB, never touches dev data)
python scripts/run_phase12_validation.py        # verify external corpus + regression set
python scripts/generate_phase12_report.py       # confusion matrix / FPR / FNR / FP-FN lists
```

See `docs/feedback_learning.md` for the full Phase 9 workflow.

**Limitations:**

- Trained on **synthetic data**; performance on real certificates is a
  preliminary estimate, not a guarantee.
- **False positives are possible** on unusual/OOD genuine certificates (e.g.,
  internally inconsistent but genuine academic documents).
- The `manual_review` review status is an advisory banding of the ML risk
  score; it does not change the model prediction and is not proof of either
  genuineness or fraud. Duplicate detection identifies reuse of the same file,
  certificate ID, or exact identity combination; it cannot detect all forms of
  forgery.
- OCR (RapidOCR, bundled) recovers text from image-heavy documents, but OCR
  quality varies with scan resolution and layout; a failed or low-confidence
  extraction is flagged for manual review rather than treated as fraud.
- The Phase 12 evidence engine is heuristic and transparent by design: tampering
  detection (JPEG artifacts / ELA / clone detection) is best-effort and can be
  fooled by heavy legitimate re-compression, external verification is **disabled
  by default**, and the engine never treats missing fields, image-only
  documents, OCR failure, or unknown issuers as fraud. It is a supplement to the
  ML verdict, not a replacement.
- The feedback loop collects labeled review evidence for future retraining; it
  does not change the current model and no candidate is auto-promoted.
- This is **not** a legal authentication verdict.