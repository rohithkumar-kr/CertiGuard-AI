# Document Extraction Pipeline (Phase 10)

## Goal

Robust text extraction for *any* certificate — including scanned and
image-heavy PDFs that previously had no usable text. The driving case: a real
Cisco Networking Academy "Introduction to modern ai" certificate whose PDF
carries only a tiny 44-character text layer while the visible content is a
rendered image. Before Phase 10 that document was extracted with zero fields
and scored `suspicious / risk 0.90`; with OCR fallback it recovers its
recipient, issuer, course, date, and certificate type and scores `genuine /
risk 0.27` — without retraining the model or adding a single Cisco-specific
rule.

## Extraction flow

```
extract_document(path, ext)
│
├─ PDF ─▶ embedded text (PyMuPDF) + visual features (first page, dpi 150)
│          │
│          _text_sufficient(text, fields)?
│            ├─ yes ─▶ method = pdf_text          (normal text-layer PDFs)
│            └─ no  ─▶ render pages (dpi 200, ≤ ocr_max_pages)
│                       │
│                       OCR (ocr_service) ─▶ text + mean line confidence
│                       │
│                       embedded + OCR text ─▶ method = hybrid
│                       OCR text only       ─▶ method = ocr
│                       no text recovered   ─▶ method = pdf_text|none (failed)
│
└─ Image ─▶ visual features + OCR (method = ocr)
```

## When OCR runs (text sufficiency)

`extraction_service._text_sufficient()` decides using
`ocr_min_text_chars` (40), `ocr_hybrid_chars` (150), and
`ocr_min_completeness` (0.4):

1. Empty text → **OCR**.
2. Fewer than 40 characters → **OCR** (a sub-40-char text layer is not
   trustworthy).
3. Otherwise, if fewer than 40% of the 5 core identity fields were recovered
   and the text is shorter than 150 characters → **OCR** (image-heavy
   certificate with a partial accessibility layer).
4. Otherwise the embedded text layer is sufficient → no OCR.

Normal text-layer PDFs (the common case) never touch OCR.

## Field recovery on OCR text

OCR text has no recipient phrases ("Awarded to …"), so two **generic**
fallbacks activate only for OCR-derived text:

- `_extract_bare_name()` — a standalone all-caps / title-case name line
  (prominent name typography), rejecting organization headings, titles,
  dates, and boilerplate.
- `_extract_course_fallback()` — the longest non-boilerplate line that is not
  the issuer, recipient, title, date, or a labeled metadata line.

These are deliberately scoped to OCR text; existing text-layer extraction is
byte-for-byte unchanged.

## Extraction metadata

Every extraction reports:

| Field | Meaning |
|---|---|
| `extraction_method` | `pdf_text` \| `ocr` \| `hybrid` \| `none` |
| `extraction_confidence` | text layer: `0.6 + 0.4 × completeness` (cap 0.95); OCR: mean line confidence (cap 0.95) |
| `extracted_text_length` | characters of extracted text |
| `extraction_completeness` | fraction of the 5 core identity fields recovered |
| `ocr_used` / `ocr_failed` / `ocr_pages` | OCR behavior |
| `extraction_confidence` level | `high` ≥ 0.7 · `medium` ≥ 0.4 · `low` < 0.4 |

Metadata is persisted in the `verifications.extraction_metadata` JSON column
and returned to the frontend as the `extraction` block in the verify and
verification-detail responses.

## Graceful failure

OCR is best-effort and can never crash verification:

- Engine detection: RapidOCR (bundled ONNX models, no external binary) is the
  default; Tesseract is used only if `OCR_ENGINE=pytesseract` or RapidOCR is
  missing.
- Every page OCR is wrapped; failures return a structured `OcrResult`.
- When OCR fails or confidence is low, the intelligence layer adds a
  `low_extraction_confidence` risk signal:
  *"Low extraction confidence — manual review recommended."*

## Missing fields are not fraud

Fields the extractor cannot find stay missing (never invented). OCR failure
or a low-completeness extraction does **not** raise the fraud probability —
it raises a manual-review advisory, so a genuine scanned certificate is
reviewed by a human instead of being auto-flagged.

## Configuration (env)

| Variable | Default | Meaning |
|---|---|---|
| `OCR_ENABLED` | `true` | master switch |
| `OCR_ENGINE` | `auto` | `auto` \| `rapidocr` \| `pytesseract` \| `none` |
| `OCR_LANGUAGES` | `en` | Tesseract language pack(s) |
| `OCR_DPI` | `200` | render resolution for OCR |
| `OCR_MAX_PAGES` | `4` | max pages rendered for OCR |
| `OCR_MIN_TEXT_CHARS` | `40` | below this → OCR |
| `OCR_HYBRID_CHARS` | `150` | short-text+low-completeness threshold |
| `OCR_MIN_COMPLETENESS` | `0.4` | completeness trust threshold |

## Model invariants

OCR text flows through the **existing** `extract_fields` →
`build_features_from_extraction` → `predict` path. It is not an ML feature,
so the 31-feature schema, the `random_forest_v3` artifact, and the 0.5
decision threshold are untouched (verified by regression tests:
`tests/test_extraction_phase10.py`).