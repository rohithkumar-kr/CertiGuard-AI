# Internal Project Report — AI-Powered Certificate Verification & Fraud Detection System

## 1. Current Architecture (as found)

The repository is a fresh monorepo with **no commits**. It contains two top-level
directories: `backend/` and `frontend/`.

```
backend/
  .env                      (empty)
  .gitignore                (empty)
  README.md                 (empty)
  requirements.txt          (empty)
  venv/                     (Python 3.13.5 virtualenv, already created)
  app/
    main.py                 (FastAPI app: GET /, POST /upload)
    api/upload.py           (EMPTY)
    core/                   (EMPTY dir)
    database/base.py        (SQLAlchemy DeclarativeBase)
    database/database.py    (EMPTY stub - only imports)
    ml/                     (EMPTY dir)
    models/certificate.py   (Certificate ORM model)
    schemas/                (EMPTY dir)
    services/file_service.py(EMPTY)
    utils/file_utils.py     (EMPTY)
  tests/                    (EMPTY dir)
  uploads/                  (EMPTY dir)
frontend/                   (COMPLETELY EMPTY)
```

### What exists and works
- `backend/app/main.py` — a minimal FastAPI app that imports/startssuccessfully.
  - `GET /` returns `{"message": "Welcome"}`
  - `POST /upload` returns only the uploaded `filename` and `content_type`.
- `backend/app/database/base.py` — declarative `Base` for SQLAlchemy.
- `backend/app/models/certificate.py` — a `Certificate` table model with fields:
  `id, original_filename, stored_filename, file_path, candidate_name, organization,
  course, status, confidence, ocr_completed, uploaded_at`.
- A Python 3.13.5 virtualenv with: `fastapi, uvicorn, sqlalchemy, psycopg2-binary,
  pydantic, python-dotenv, python-multipart`.

### What is broken / incomplete
- `app/database/database.py` — imports exist but no engine/session/DATABASE_URL wiring.
- `app/api/upload.py`, `app/services/file_service.py`, `app/utils/file_utils.py` — empty.
- `/upload` does no processing, validation, or storage.
- No `.env` configuration, no `requirements.txt`, no `.gitignore`.
- No tests exist.

### What is missing (entirely)
- Dataset (raw/processed)
- ML model, preprocessing, feature engineering, training, evaluation, serialization
- Experiment tracking / model versioning / model registry
- Certificate processing (file validation, safe storage, text/visual extraction)
- Inference/verification API (`POST /verify`)
- Frontend (upload UI)
- Database wiring + verification persistence
- Monitoring / logging / metrics
- Tests
- Docker / CI
- README / documentation
- Sample/demo assets

### Security observations
- No secrets committed. `.env` is empty. No hardcoded keys found.
- No input validation on `/upload` (unrestricted file type/size) — must be fixed.
- No error handling — stack traces could leak.

## 2. Recommended Final Architecture

```
repo root/
  backend/                       # FastAPI backend + ML pipeline (existing venv reused)
    app/                         # API application (extend existing skeleton)
      api/         routes (verify, health, model info, metrics, verifications)
      core/        config, logging, security
      database/    engine, session, base
      models/      ORM models (certificate, verification)
      schemas/     Pydantic request/response models
      services/    file handling, extraction, feature building, verification
      ml/          model loading/prediction
      utils/       file validation, text helpers
    src/           # ML pipeline (data → features → training → inference)
      data/        make_dataset.py (synthetic data generation)
      features/    build_features.py
      models/      train_model.py, evaluate_model.py
      training/    run_pipeline.py
      inference/   predict.py
    data/raw/      raw synthetic dataset
    data/processed/engineered features
    models/        serialized artifacts (model, scaler, features, metadata)
    configs/       settings (yaml/env)
    monitoring/    logs, experiment/run tracking
    scripts/       run scripts + sample certificate generator
    tests/         pytest suite
    requirements.txt, .env.example, .gitignore, README.md, Dockerfile
  frontend/        # React + Vite SPA (upload → verify → result)
  docs/            # this report
  .github/workflows/ci.yml
  docker-compose.yml
```

Design decisions:
- **Keep** the existing FastAPI `app/` layout and `Certificate` model; extend rather
  than rewrite.
- **SQLite** (via SQLAlchemy) instead of Postgres for zero-setup reproducibility;
  `DATABASE_URL` is configurable so Postgres can be used later.
- **Classical ML** (Logistic Regression + Random Forest baseline) on engineered
  features — appropriate for a small tabular fraud-detection dataset and explainable.
- **Lightweight experiment tracking** (JSONL runs under `monitoring/mlruns/`) that
  records params, metrics, artifacts, and model versions. MLflow is not used because
  it adds heavy infra; the tracker format is documented and swappable.
- **Synthetic dataset**: no public dataset of labeled educational certificates exists
  for this problem; we generate a realistic, reproducible synthetic dataset and
  clearly document that it is synthetic/prototype data.
- **Certificate processing**: PDF text extraction via PyMuPDF; image/visual features
  (blank ratio, sharpness, noise, color anomaly) via Pillow/numpy; text-derived
  features when OCR-capable text is present. No heavyweight OCR stack (tesseract
  optional, not required).
- **Frontend**: React + Vite served with a dev proxy; production build servable by
  the backend.

## 3. Feature Set (aligned with generated data)

| Feature | Description |
|---|---|
| cert_id_format_valid | certificate id matches expected pattern |
| cert_id_checksum_valid | id check-digit / checksum |
| issuer_known | issuer institution recognized |
| issue_year_valid | issue year within plausible range |
| date_consistency_valid | issue date not in future / pre-founding |
| candidate_name_present | candidate name extracted |
| course_present | course/program extracted |
| organization_present | organization extracted |
| text_field_completeness | fraction of expected fields present |
| marks_pattern_valid | marks ≤ total, plausible |
| grade_consistency_valid | grade matches marks band |
| suspicious_keyword_count | count of fraud-ish phrases |
| suspicious_url_present | external/contact links in text |
| signature_present | signature field detected |
| seal_present | seal/stamp detected |
| qr_present | QR/barcode detected |
| visual_blank_ratio | low ink coverage (blank document) |
| visual_sharpness | blur/photo-copy detection |
| visual_noise | scanner noise level |
| visual_color_anomaly | unusual dominant color |
| text_duplicate_similarity | similarity to known duplicates (0 in prototype) |
| issuer_domain_trust | trust score of issuer domain |

## 4. Priority Order for Implementation

1. Repo scaffolding (requirements, gitignore, env, config) — unblock everything
2. Synthetic data generation + feature engineering
3. ML training/evaluation/serialization + experiment tracking
4. Inference module
5. Certificate processing (extraction + features)
6. Backend wiring (DB, services, `/api/verify`, monitoring, security)
7. Tests
8. Frontend
9. Sample certificate generator
10. README/docs
11. Docker + CI
12. End-to-end verification
