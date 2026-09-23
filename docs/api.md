# API Reference

Base URL: `http://127.0.0.1:8000` (configurable via `VITE_API_BASE_URL` in the
frontend; the Vite dev server proxies `/api` to the backend).

Interactive docs (development only): `http://127.0.0.1:8000/docs`.

All responses are JSON. Errors return `{"detail": "<user-safe message>"}`.

## GET /api/health

Server and model availability.

```json
{
  "status": "ok",
  "app": "AI Certificate Verification System",
  "model_version": "random_forest_v3",
  "model_loaded": true
}
```

## GET /api/model/info

Active model metadata.

```json
{
  "model_version": "random_forest_v3",
  "model_name": "random_forest",
  "features": ["cert_id_format_valid", "...", "certificate_structure_completeness"],
  "metrics": { "accuracy": 0.9287, "precision": 0.9422, "recall": 0.8281, "f1": 0.8815, "confusion_matrix": [[531, 13], [44, 212]] },
  "created_at": "2026-08-18T14:59:48.787268+00:00"
}
```

## POST /api/verify

Upload **exactly one** certificate file (multipart form, field name `file`).

- Allowed extensions: `.pdf`, `.png`, `.jpg`, `.jpeg`.
- Max size: 10 MB (env `MAX_UPLOAD_SIZE_MB`).
- Magic bytes must match the declared extension.

Request:

```bash
curl -X POST http://127.0.0.1:8000/api/verify -F "file=@certificate.pdf"
```

Response (200):

```json
{
  "verification_id": "V2026-8F3C9A1B",
  "prediction": "genuine",
  "label": "GENUINE",
  "risk_score": 0.2494,
  "confidence": 0.7506,
  "message": "AI-based preliminary verification: no strong fraud-risk signals were found. This is a preliminary automated result, not a legal authenticity guarantee.",
  "model_version": "random_forest_v3",
  "certificate_type": { "academic": 1, "completion": 0, "training": 0, "technical": 0 },
  "extracted": { "candidate_name": "...", "organization": "...", "course": "..." },
  "warnings": [],
  "created_at": "2026-08-18T12:00:00",
  "review_status": "low_risk",
  "recommended_action": { "action": "accept", "heading": "Accept", "message": "..." },
  "intelligence": {
    "certificate_type": { "flags": { "academic": 1, "completion": 0, "training": 0, "technical": 0, "online": 0, "workshop": 0 }, "primary": "academic" },
    "identity": {
      "recipient": { "label": "Recipient", "value": "John Walker", "present": true },
      "issuer": { "label": "Issuer", "value": "University of Cambridge", "present": true },
      "course": { "label": "Course / Title", "value": "Computer Science", "present": true },
      "issue_date": { "label": "Issue Date", "value": "2022-06-15", "present": true },
      "certificate_id": { "label": "Certificate ID", "value": "CERT-2022-123455", "present": true },
      "marks": { "label": "Marks / Grade", "value": "95 / 100 (A)", "present": true }
    },
    "structural_signals": {
      "signature": { "label": "Signature", "present": true },
      "seal": { "label": "Seal / Stamp", "present": true },
      "qr": { "label": "QR / Barcode", "present": true },
      "url": { "label": "External URL", "present": false }
    },
    "quality_indicators": {
      "blank_document": false,
      "text_extraction_quality": "ok",
      "text_present": true,
      "visual_quality": "ok",
      "noise": 0.0,
      "sharpness": 0.0,
      "blank_ratio": 0.0,
      "color_anomaly": false,
      "processing_warnings": []
    },
    "consistency_findings": [],
    "structure_completeness": 1.0,
    "issuer_status": "ok",
    "certificate_id_status": "ok",
    "date_status": "ok",
    "recipient_status": "ok",
    "course_status": "ok"
  },
  "positive_signals": [ { "key": "recognized_issuer", "label": "Recognized issuer", "status": "ok", "severity": "low", "detail": "..." } ],
  "risk_signals": [],
  "duplicate": { "is_duplicate": false, "duplicate_of": null, "duplicate_type": null },
  "ood_status": "normal",
  "review_priority": "low",
  "extraction_completeness": 1.0,
  "extraction": {
    "method": "pdf_text",
    "confidence": 0.95,
    "confidence_level": "high",
    "text_length": 1087,
    "completeness": 1.0,
    "ocr_used": false,
    "ocr_failed": false,
    "ocr_pages": 0,
    "fields_detected": 5,
    "fields_total": 5
  }
}
```

`prediction` is `genuine` (risk < 0.5) or `suspicious` (risk ≥ 0.5). The
`message` explains that this is a **preliminary AI assessment, not legal
authentication**; suspicious results recommend manual review.

**Phase 8 intelligence fields:**

- `review_status` — three-level advisory status on top of the ML prediction:
  `low_risk`, `manual_review`, or `high_risk`. The ML `prediction` and
  `risk_score` are unchanged; this is a separate guidance layer.
- `recommended_action` — `{action, heading, message}` where `action` is
  `accept`, `manual_review`, or `investigate`.
- `intelligence` — structured certificate intelligence:
  - `certificate_type.flags` — independent flags for academic/completion/
    training/technical/online/workshop; `primary` is the single best label.
  - `identity` — extracted recipient, issuer, course, date, certificate ID,
    marks/grade with `present` flags (missing fields are reported as missing,
    never as fraud).
  - `structural_signals` — signature/seal/QR/URL presence.
  - `quality_indicators` — blank-document flag, text extraction quality,
    visual quality, noise, sharpness, color anomaly.
  - `consistency_findings` — structured contradictions (future date,
    marks > total, grade/marks mismatch, invalid certificate ID, unknown
    issuer, missing expected structure).
  - `*_status` — per-field status (`ok` / `missing` / `warning`).
- `positive_signals` / `risk_signals` — detected trust and risk indicators
  (explanation engine). Wording is "detected risk signal" / "requires manual
  review", never "proves fraud".
- `duplicate` — reuse detection: `{is_duplicate, duplicate_of, duplicate_type}`
  where `duplicate_type` is `file` (exact content hash), `cert_id` (same
  certificate ID), or `identity` (same recipient+issuer+course+date).

**Phase 9 advisory fields (never part of the ML prediction):**

- `ood_status` — out-of-distribution advisory: `normal` | `unusual` |
  `insufficient_information`. Informational only; it is never used as a
  feature and never treated as proof of fraud.
- `review_priority` — triage for human review: `low` | `medium` | `high`.
  Separate from `prediction` / `review_status`.
- `extraction_completeness` — fraction (0..1) of identity fields extracted.

**Phase 10 extraction diagnostics:**

- `extraction` — how the document text was obtained and how reliable it is:
  - `method` — `pdf_text` (embedded text layer), `ocr` (rendered pages OCR'd),
    `hybrid` (embedded + OCR combined), or `none` (no text recovered).
  - `confidence` — 0..1 extraction confidence (text layer:
    `0.6 + 0.4 × completeness` capped at 0.95; OCR: mean OCR line confidence).
  - `confidence_level` — `high` (≥ 0.7) | `medium` (≥ 0.4) | `low` (< 0.4).
  - `text_length` — characters of extracted text.
  - `completeness` — fraction (0..1) of the 5 core identity fields recovered.
  - `ocr_used` / `ocr_failed` / `ocr_pages` — whether OCR ran, whether every
    page failed, and how many pages were processed.
  - `fields_detected` / `fields_total` — core identity fields recovered.
- When extraction quality is poor (OCR failed, no text, or confidence < 0.4),
  the intelligence layer adds a `low_extraction_confidence` risk signal:
  *"Low extraction confidence — manual review recommended."* Missing fields
  are treated as an extraction limitation, not as fraud evidence, and
  extraction quality is never fed into the ML features.

**Phase 12 evidence block (additive — all prior fields unchanged):**

The response adds a `verification_evidence` object that is a snapshot of the
evidence engine's final assessment:

```json
"verification_evidence": {
  "assessment": "LIKELY_GENUINE",
  "confidence": 0.87,
  "category_status": {
    "ml": "PASS", "extraction": "PASS", "structure": "PASS",
    "semantic": "PASS", "forensics": "PASS", "visual": "PASS",
    "tampering": "PASS", "qr": "WARNING", "issuer": "PASS",
    "anomaly": "PASS", "external": "UNKNOWN", "duplicate": "PASS"
  },
  "evidence_items": [
    { "category": "issuer", "status": "PASS", "severity": "low",
      "key": "issuer_known", "detail": "Issuer matched the registry" }
  ]
}
```

- `assessment` — `LIKELY_GENUINE` | `LIKELY_SUSPICIOUS` |
  `REQUIRES_VERIFICATION` | `INSUFFICIENT_EVIDENCE` (see
  `docs/evidence_fusion.md` for the decision rules).
- `confidence` — 0..1 aggregate confidence of the evidence engine.
- `category_status` — per-category status: `PASS` | `WARNING` | `FAIL` |
  `UNKNOWN`.
- `evidence_items` — human-readable evidence lines (category, status,
  severity, key, detail) used by the reviewer UI.

The snapshot is persisted in the `evidence_json` column on the verification
record and surfaced on the detail endpoint
(`GET /api/verifications/{verification_id}` → `evidence_details`). It is a
supplement to the ML verdict, never a replacement: `prediction`, `risk_score`
and `review_status` behave exactly as before.

Error responses:

| Status | Condition | Example detail |
|---|---|---|
| 400 | unsupported extension / empty / malformed / oversized / multiple files | `"The uploaded file is not valid."` / `"Exactly one file must be uploaded."` |
| 422 | missing file / malformed multipart request | `"Invalid request. A valid file upload is required."` |
| 503 | model artifacts unavailable | `"The verification model is not available right now. Please try again later."` |
| 500 | unexpected error | `"An unexpected error occurred. Please try again later."` |

## GET /api/verifications

Recent verification records, newest first.

Query params:

- `limit` (int, 1–100, default 20)
- `search` — substring match on filename
- `prediction` — `genuine` | `suspicious` | `error`
- `review_status` — `low_risk` | `manual_review` | `high_risk`
- `certificate_type` — `academic` | `completion` | `training` | `technical` |
  `online` | `workshop`
- `issuer` — substring match on the extracted issuer
- `date_from` / `date_to` — `YYYY-MM-DD`; filters on the verification timestamp
- `risk_min` / `risk_max` — float 0–1 risk-score range
- `sort` — `newest` (default) | `oldest`

```bash
curl "http://127.0.0.1:8000/api/verifications?limit=5&review_status=manual_review"
curl "http://127.0.0.1:8000/api/verifications?issuer=cambridge&risk_min=0.3"
```

Response (list):

```json
[
  {
    "verification_id": "V2026-8F3C9A1B",
    "filename": "certificate.pdf",
    "prediction": "genuine",
    "risk_score": 0.2494,
    "confidence": 0.7506,
    "model_version": "random_forest_v3",
    "created_at": "2026-08-18T12:00:00",
    "review_status": "low_risk",
    "issuer": "University of Cambridge",
    "certificate_type": "{\"academic\": 1, ...}",
    "duplicate_of": null,
    "duplicate_type": null,
    "ood_status": "normal",
    "review_priority": "low",
    "reviewer_label": null,
    "reviewed_at": null,
    "is_disagreement": null
  }
]
```

Phase 9 additions on each record: `ood_status`, `review_priority`
(advisory indicators), and `reviewer_label` / `reviewed_at` /
`is_disagreement` (populated once a human review has been submitted).

## GET /api/verifications/{verification_id}

Full detail for a single verification — used by the reviewer workflow
(Phase 9H). Includes the persisted intelligence snapshot and any review
decision.

```bash
curl "http://127.0.0.1:8000/api/verifications/V2026-8F3C9A1B"
```

Response:

```json
{
  "verification_id": "V2026-8F3C9A1B",
  "filename": "certificate.pdf",
  "prediction": "genuine",
  "label": "GENUINE",
  "risk_score": 0.2494,
  "confidence": 0.7506,
  "model_version": "random_forest_v3",
  "created_at": "2026-08-18T12:00:00",
  "error": null,
  "review_status": "low_risk",
  "issuer": "University of Cambridge",
  "certificate_type": "{\"academic\": 1, ...}",
  "extracted_info": "{\"candidate_name\": \"...\", ...}",
  "duplicate_of": null,
  "duplicate_type": null,
  "ood_status": "normal",
  "review_priority": "low",
  "intelligence": { "certificate_type": { ... }, "identity": { ... }, "quality_indicators": { ... }, ... },
  "positive_signals": [ ... ],
  "risk_signals": [ ... ],
  "duplicate": { "is_duplicate": false, "duplicate_of": null, "duplicate_type": null },
  "extraction": { "method": "pdf_text", "confidence": 0.95, "confidence_level": "high", "text_length": 1087, "completeness": 1.0, "ocr_used": false, "ocr_failed": false, "ocr_pages": 0, "fields_detected": 5, "fields_total": 5 },
  "evidence_details": {
    "assessment": "LIKELY_GENUINE",
    "category_status": { "ml": "PASS", "issuer": "PASS", "duplicate": "PASS" },
    "evidence_items": [ { "category": "issuer", "status": "PASS", "severity": "low", "key": "issuer_known", "detail": "Issuer matched the registry" } ]
  },
  "reviewer_label": null,
  "reviewer_note": null,
  "reviewed_at": null,
  "is_disagreement": null
}
```

`400` if the verification does not exist.

## POST /api/verifications/{verification_id}/feedback

Record a human-review decision (Phase 9B). Feedback **never** modifies the ML
model, the prediction, or the risk score; it is stored as immutable evidence
next to the verification.

Request:

```bash
curl -X POST "http://127.0.0.1:8000/api/verifications/V2026-8F3C9A1B/feedback" \
  -H "Content-Type: application/json" \
  -d '{"reviewer_label": "confirmed_genuine", "reviewer_note": "Matches issuer records"}'
```

Body:

- `reviewer_label` (required) — one of:
  - `confirmed_genuine` — reviewer confirms genuine
  - `confirmed_suspicious` — reviewer confirms suspicious
  - `uncertain` — reviewer cannot decide (excluded from training candidates)
- `reviewer_note` (optional, max 2000 chars)

Response (200):

```json
{
  "verification_id": "V2026-8F3C9A1B",
  "reviewer_label": "confirmed_genuine",
  "reviewer_note": "Matches issuer records",
  "reviewed_at": "2026-08-19T14:00:00",
  "original_prediction": "genuine",
  "original_risk_score": 0.2494,
  "model_version": "random_forest_v3",
  "certificate_type": "academic",
  "extraction_completeness": 1.0,
  "review_status": "low_risk",
  "ood_status": "normal",
  "review_priority": "low",
  "is_disagreement": false,
  "split": null,
  "dataset_batch": null
}
```

`is_disagreement` is `true` when a decisive reviewer label contradicts the AI
prediction. `split` / `dataset_batch` are populated once the example is
included in a candidate training dataset.

Errors:

| Status | Condition |
|---|---|
| 400 | unknown verification / failed verification / already reviewed / invalid label |
| 422 | missing or malformed JSON body |

## GET /api/feedback/summary

Summary counts over the reviewer feedback collection (Phase 9B).

```json
{
  "total_reviewed": 12,
  "not_reviewed": 8,
  "confirmed_genuine": 7,
  "confirmed_suspicious": 4,
  "uncertain": 1,
  "decisive_reviews": 11,
  "agreement_count": 10,
  "disagreement_count": 1,
  "agreement_rate": 0.9091,
  "disagreement_rate": 0.0909
}
```

Rates are `null` when there are no decisive reviews yet.

## GET /api/feedback/analytics

Monitoring view over reviewed certificates (Phase 9I). Percentages are only
reported when the sample count is high enough (default minimums: 10 decisive
samples overall, 5 per sub-group); otherwise `sufficient` is `false` and
percentage metrics are omitted rather than invented.

```json
{
  "summary": { "...": "same shape as /api/feedback/summary" },
  "overall": {
    "n": 12,
    "confusion_matrix": { "tn": 3, "fp": 1, "fn": 0, "tp": 7 },
    "genuine_truth": 7,
    "suspicious_truth": 5,
    "genuine_pred": 8,
    "suspicious_pred": 4,
    "sufficient": true,
    "genuine_precision": 0.875,
    "genuine_recall": 1.0,
    "genuine_f1": 0.9333,
    "suspicious_precision": 0.75,
    "suspicious_recall": 0.6,
    "suspicious_f1": 0.6667,
    "false_positive_rate": 0.25,
    "false_negative_rate": 0.0,
    "accuracy": 0.8333,
    "disagreement_count": 1
  },
  "by_certificate_type": { "academic": { "...": "per-group _aggregate" } },
  "by_issuer": { "University of Cambridge": { "...": "per-group _aggregate" } },
  "by_review_status": { "low_risk": { "...": "per-group _aggregate" } },
  "by_priority": { "low": { "...": "per-group _aggregate" } },
  "by_extraction_completeness": {
    "low": { "...": "per-group _aggregate" },
    "medium": { "...": "per-group _aggregate" },
    "high": { "...": "per-group _aggregate" },
    "unknown": { "...": "per-group _aggregate" }
  },
  "average_extraction_completeness": 0.94,
  "ood_distribution": { "normal": 11, "unusual": 1 },
  "review_priority_distribution": { "low": 9, "medium": 2, "high": 1 },
  "manual_review_rate": 0.6,
  "minimum_metric_samples": 10
}
```

`manual_review_rate` = reviewed examples / successful verifications.

## GET /api/verifications/summary

Summary counts over the verification history. Supports the same filter params
as `/api/verifications` (`search`, `prediction`, `review_status`,
`certificate_type`, `issuer`, `date_from`, `date_to`, `risk_min`, `risk_max`).

```json
{
  "total": 26,
  "genuine_count": 7,
  "suspicious_count": 13,
  "manual_review_count": 2,
  "average_risk_score": 0.6095
}
```

## GET /api/metrics

Aggregate monitoring over all persisted verifications.

```json
{
  "total_verifications": 26,
  "genuine_count": 7,
  "suspicious_count": 13,
  "error_count": 6,
  "prediction_distribution": { "genuine": 7, "suspicious": 13 },
  "certificate_type_distribution": { "academic": 2, "completion": 5 },
  "average_risk_score": 0.6095,
  "average_confidence": 0.6102,
  "model_versions": { "random_forest_v3": 20 },
  "recent": [ { "verification_id": "...", "prediction": "...", "risk_score": 0.0, "confidence": 0.0, "model_version": "...", "created_at": null, "filename": null } ],
  "review_status_distribution": { "low_risk": 14, "manual_review": 2, "high_risk": 4 },
  "average_extraction_completeness": 0.81,
  "issuer_distribution": { "University of Cambridge": 8, "CloudForge Academy": 3 },
  "manual_review_rate": 0.1
}
```

Fields:

- `total_verifications` — every attempt (success + error).
- `genuine_count` / `suspicious_count` — successful predictions only.
- `error_count` — failed verifications (recorded with `prediction: "error"`).
- `prediction_distribution` — counts by prediction value.
- `certificate_type_distribution` — counts of flagged certificate types
  (academic/completion/training/technical; one record can flag several).
- `average_risk_score` / `average_confidence` — mean over successful rows.
- `model_versions` — usage by model version.
- `recent` — the 10 most recent records.
- `review_status_distribution` — counts by `low_risk` / `manual_review` /
  `high_risk`.
- `average_extraction_completeness` — mean fraction of identity fields
  extracted (recipient, issuer, course, date, certificate ID).
- `issuer_distribution` — top issuers by count (max 15).
- `manual_review_rate` — `manual_review` rows / successful rows.

## CORS

Allowed origins default to `http://localhost:5173`, `http://127.0.0.1:5173`,
`http://localhost:8000` (env `CORS_ORIGINS`). The API echoes
`Access-Control-Allow-Origin` for the configured origins and answers
preflight `OPTIONS` requests, so the frontend can call the API cross-origin.