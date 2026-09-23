# Phase 10 Report — Robust Document Extraction + OCR Fallback

## Problem (critical finding)

A real **Cisco Networking Academy "Introduction to modern ai" certificate** was
uploaded and produced a false-positive fraud flag:

| | Before Phase 10 |
|---|---|
| Embedded text layer | 44 chars only (`ROHITH KUMAR K R IT` / `Issued on: Jan 27, 2025`) — the visible content is a rendered image |
| Extracted fields | **none detected** |
| Prediction / risk | **suspicious / 0.9038** |
| OOD | unusual |

The root cause was purely an extraction gap: image-heavy PDFs never reached
OCR, so the model saw a "missing everything" certificate and scored it as
fraud. No fraud was involved; the document is a real Cisco credential.

## What was delivered

1. **Centralized OCR layer** — `backend/app/services/ocr_service.py`.
   - `OCR_ENABLED` master switch; `OCR_ENGINE` = `auto` (RapidOCR/ONNX by
     default, Tesseract optional), `OCR_LANGUAGES`, `OCR_DPI`, `OCR_MAX_PAGES`.
   - RapidOCR bundles its ONNX models — **no external Tesseract binary needed**
     (Tesseract is not installed on this machine).
   - Every call is best-effort and returns a structured `OcrResult`; it can
     never crash verification.

2. **OCR fallback in extraction** — `backend/app/services/extraction_service.py`.
   - `_text_sufficient()` decides when OCR runs: empty text, < 40 chars, or a
     short text layer with few recovered core fields. Normal text PDFs never
     touch OCR.
   - PDF flow: embedded text → (if insufficient) render pages at `OCR_DPI`,
     OCR each, combine with embedded text (`hybrid`) or use alone (`ocr`).
   - Image flow: always OCR.
   - **Extraction metadata** on every result: `extraction_method`
     (`pdf_text`/`ocr`/`hybrid`/`none`), `extraction_confidence`,
     `extracted_text_length`, `extraction_completeness`, `ocr_used`,
     `ocr_failed`, `ocr_pages`.

3. **Generic OCR-path field recovery** (only for OCR text, so existing
   text-layer extraction is byte-for-byte unchanged):
   - Month abbreviations (`Jan 27, 2025` → `2025-01-27`).
   - Standalone all-caps / title-case **name line** (`_extract_bare_name`).
   - Course-title line fallback (`_extract_course_fallback`).
   - Reject single-word generic issuer nouns (`Academy`, `University`, …) and
     comma-role headings (`Director, Acme`) so OCR-split headings don't yield a
     bogus issuer.

4. **Intelligence layer** — `backend/app/services/intelligence_service.py`.
   - `_quality_indicators` reports `extraction_method`, `extraction_confidence`,
     `ocr_used`, `ocr_failed`; `text_extraction_quality` = ok/failed/missing.
   - New **`low_extraction_confidence`** medium risk signal:
     *"Low extraction confidence — manual review recommended."* raised when OCR
     fails, text is absent, or confidence < 0.4. **Missing fields remain
     missing and are never treated as fraud; extraction quality never enters the
     ML features.**

5. **Persistence + API** — `verifications.extraction_metadata` column (idempotent
   migration); `extraction` diagnostics block in `/api/verify` and
   `/api/verifications/{id}` responses (`method`, `confidence`,
   `confidence_level`, `text_length`, `completeness`, `ocr_used`, `ocr_failed`,
   `ocr_pages`, `fields_detected`, `fields_total`).

6. **Frontend** — `ResultCard` shows extraction-method / confidence / fields-
   detected / OCR-failed badges; `ExtractedInfo` shows the extraction
   diagnostics block.

7. **Docs** — `docs/extraction_pipeline.md` (new), plus `architecture.md`,
   `ml_pipeline.md`, `api.md`, `README.md`, `.env.example`, `requirements.txt`.

## Result on the real Cisco certificate

Re-run of the actual uploaded file through the unchanged model:

| | After Phase 10 |
|---|---|
| Extraction | **hybrid** (embedded + OCR), confidence **0.85** (high), 1102 chars |
| Fields detected | **4/5** — recipient `ROHITH KUMAR K R IT`, issuer `CISco`*, course `Machine Learning`, date `2025-01-27`, cert type `Certificate of Course Completion` |
| Prediction / risk | **genuine / 0.2671** |
| Review status | **manual_review** (honest: Cisco is not a known issuer → `unknown_issuer` signals; OOD = unusual) |

\* The OCR engine splits the header "Cisco Networking Academy" across three
lines; the generic extractor picks the strongest fragment. No Cisco-specific
rule was added.

The same pipeline recovered **all** core fields in the reproducible test PDFs
(`tests/test_extraction_phase10.py`), including a fully image-only PDF.

## Model invariants (verified by tests)

- Model artifact SHA-256 unchanged:
  `e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337`
  (`random_forest_v3/model.joblib`).
- Feature schema: still **31 features**.
- Decision threshold: still **0.5**.
- `random_forest_v3` behavior is unmodified — OCR only improves the text
  feeding the existing features. No retraining, no new features, no
  Cisco-specific rules, no forced-genuine logic, no weakened fraud detection.

## Tests

Full backend suite: **206 passed** (186 existing + 20 new in
`backend/tests/test_extraction_phase10.py` covering text sufficiency, normal /
image-only / tiny-layer PDFs, OCR fallback, graceful OCR failure, the
`low_extraction_confidence` signal, extraction metadata in API + DB, and model
invariants). Frontend: `npm run build` (tsc + vite) passes.

## Files changed (Phase 10)

- `backend/app/core/config.py` — OCR settings.
- `backend/app/services/ocr_service.py` — **new**, centralized OCR engine.
- `backend/app/services/extraction_service.py` — OCR fallback, hybrid,
  metadata, OCR-path field recovery, issuer hardening.
- `backend/app/services/intelligence_service.py` — extraction quality
  indicators + `low_extraction_confidence` signal.
- `backend/app/services/verification_service.py` — extraction diagnostics +
  persistence.
- `backend/app/models/verification.py` / `backend/app/database/database.py` —
  `extraction_metadata` column + idempotent migration.
- `backend/app/schemas/verification.py` / `backend/app/api/routes.py` —
  `extraction` block in API responses.
- `frontend/src/types/index.ts`, `frontend/src/components/ResultCard.tsx`,
  `frontend/src/components/ExtractedInfo.tsx`, `frontend/src/index.css` —
  extraction diagnostics UI.
- `backend/requirements.txt` — `rapidocr_onnxruntime`, `onnxruntime`.
- `backend/.env.example` — OCR variables.
- `backend/tests/test_extraction_phase10.py` — **new**, 20 tests.
- Docs: `docs/extraction_pipeline.md` (new), `docs/architecture.md`,
  `docs/ml_pipeline.md`, `docs/api.md`, `README.md`.

## Verification commands

```bash
cd backend
venv\Scripts\python -m pytest tests -q          # 206 passed
cd ..\frontend
npm run build                                    # tsc + vite build pass
```