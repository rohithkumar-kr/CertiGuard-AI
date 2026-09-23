# Diagnostic Report: Cisco CCNA Certificate False Positive

## Symptom

A second legitimate Cisco certificate — `CCNA-_Introduction_to_Networks.pdf`
(record `V2026-6D76E460`, stored
`backend/uploads/2c857804dcbd498bb83e5517815ed206.pdf`) — was classified as
`suspicious` by the Phase 10 pipeline. User report suggested risk ~0.90 with no
fields detected; the actual reproduced behaviour through `/api/verify` was:

| Field | Value |
| --- | --- |
| prediction | `suspicious` |
| risk_score | `0.550` |
| OOD | `unusual` |
| review | `high_risk` |
| certificate_type | `completion` |
| extracted fields | 3/5 (recipient, issuer, date) |
| extraction method | `pdf_text`, confidence `0.84` (high) |
| course / title / cert_id | missing |

The reported ~0.90 corresponds to the stale pre-Phase-10 run of the *first*
Cisco certificate (no extraction metadata); the CCNA certificate is the new,
genuinely failing one.

## Investigation

1. Located the file (the only Cisco-family PDF in `backend/uploads`) and
   reproduced the `0.55 / suspicious` result through the real API.
2. Extracted the embedded text layer (294 chars, completeness 0.6):
   `"…for successfully completing\nCCNA: Introduction to Networks\noffered by
   Chennai Institute of Technology…"`. The text is sufficient, so OCR was
   correctly skipped — **this is not an OCR failure**.
3. Compared feature vectors of the five control certificates:
   - `course_present` and `completion_title_present` were the only structural
     deltas separating CCNA (risk 0.550) from genuine controls (0.22–0.27).
   - Both fraud controls have a title too yet stay high-risk (0.99+) because
     date/issuer/quality features dominate — so *fraud detection does not
     depend on course presence*.
4. Feature ablation through the actual model: flipping only
   `course_present` 0→1 drops CCNA risk from `0.550` to `0.305` (genuine).

### Root cause

`CCNA: Introduction to Networks` matches no entry in the fixed
`COURSE_KEYWORDS` list, and the OCR-only course-title fallback was gated to
OCR text (`allow_bare_name=True`). The PDF-layer path therefore produced
`course_present = 0`, leaving the certificate just above the 0.5 threshold.
A generic, layout-independent course extractor was missing for embedded-text
certificates.

## Fix (general-purpose, no certificate-specific bypass)

`backend/app/services/extraction_service.py` — added `_extract_course_phrase`
plus `_COURSE_LABEL_RE` / `_COURSE_PHRASE_RE`, run on **all** text (PDF layer
and OCR alike) when no keyword matched:

- **Labeled fields**: `Course:`, `Program:`, `Subject:`, `Track:`, … (`:`/`.`/`-` delimited).
- **Completion phrases**: `for successfully completing`, `completing`,
  `completed`, `completion of`, … followed by a genuinely uppercase
  title-case course line (the `(?-i:[A-Z])` guard prevents matching a
  lowercase connector such as `the`/`all`).

Applied before the existing OCR-only fallback; keyword matches are unchanged.

## Before / After

| Case | course | risk | prediction |
| --- | --- | --- | --- |
| CCNA certificate (before) | missing | 0.550 | suspicious |
| CCNA certificate (after) | `CCNA: Introduction to Networks` | 0.305 | **genuine** |
| Phase 10 Cisco cert (after) | `Introduction to modern ai` | 0.267 | genuine |
| Genuine AWS (after) | `AWS` | 0.223 | genuine |
| Fraud degree mill | none | 0.993 | suspicious |
| Fraud instant cert | none | 0.997 | suspicious |
| Fraud for sale | `AWS` | 1.000 | suspicious |
| Fraud pay now | `Leadership` | 0.997 | suspicious |

Fraud certificates stay suspicious even when the generic extractor yields a
course (verified: a fraud completion cert with `CCNA: Introduction to Networks`
+ future date → risk 0.937, suspicious).

## Regression tests (added)

`backend/tests/test_extraction_phase10.py` (+6):

- generic phrase extraction of the CCNA course
- generic labeled-course extraction
- phrase regex does not match lowercase connectors (`the Physics program`, `all assignments`)
- full API verification of a CCNA-format certificate → genuine, course/org/date extracted, `pdf_text` method
- Phase 10 image-only Cisco certificate still genuine through OCR path
- fraud certificate with a detectable course still suspicious

## Invariants confirmed

- Model artifact SHA-256 `e402dca2…` unchanged; no model change, no retrain.
- Feature schema still 31 columns; decision threshold still 0.5.
- Backend suite: **212 passed** (206 before + 6 new). Frontend build passes.
- Missing fields still stay missing; OCR outputs still feed no new ML features.