# Diagnostic Report: Python Essentials Image-Heavy False Positive

## Symptom

`PythonEssentials1Update20250123-28-a15e7b.pdf` (record `V2026-6F60A8D2`,
stored `backend/uploads/27adfee8aad846c986066f265702f4f7.pdf`, 1.2 MB, 1 page)
was classified `suspicious` at ~78% risk.

The PDF is **image-heavy**: its parsed text layer is only 44 chars
(`"ROHITH KUMAR K R IT\nIssued on: Jan 23, 2025\n"`). The rendered page shows
Cisco Networking Academy / Python Institute branding, "Statement of
Achievement", Python Essentials 1, signature, QR badge, and issue date — all
inside the raster image, so they only exist for the pipeline after OCR.

## Complete pipeline for this exact PDF

| Stage | Result |
| --- | --- |
| PDF text layer | 44 chars (name + "Issued on: Jan 23, 2025") |
| Method selected | `hybrid` (`pdf_text` layer + RapidOCR), `ocr_used=True`, 1 page |
| OCR output | ~970 chars incl. the jumbled logo lines and the sentence `"…for completing the Python Essentials 1 course, provided by Cisco Networking Academy in collaboration with OpenEDG Python Institute."` |
| Extraction confidence | 0.8391 (high), completeness 0.6 |
| recipient | `ROHITH KUMAR K R IT` |
| issuer | **empty** (the failure) |
| course | `Python Essentials 1` |
| issue date | `2025-01-23` |
| cert ID | none (this credential has none) |
| certificate type | `training` |
| QR/signature/seal | 0 (text-layer heuristics; the badge/signature are pixels, not literals) |
| Visual features | blank_ratio 0.0128, sharpness 1.0, noise 0.0819, color_anomaly 0 — **not anomalous** |

## Feature vector going into random_forest_v3 (31 features)

`cert_id_format_valid=0, cert_id_checksum_valid=0, issuer_known=0,
issue_year_valid=1, date_consistency_valid=1, candidate_name_present=1,
course_present=1, organization_present=0, text_field_completeness=0.6667,
marks_pattern_valid=0, grade_consistency_valid=0, suspicious_keyword_count=0,
suspicious_url_present=0, signature_present=0, seal_present=0, qr_present=0,
visual_blank_ratio=0.0128, visual_sharpness=1.0, visual_noise=0.0819,
visual_color_anomaly=0, text_duplicate_similarity=0.0, issuer_domain_trust=0.0,
certificate_type_academic=0, certificate_type_completion=0,
certificate_type_training=1, certificate_type_technical=0, recipient_present=1,
completion_date_present=1, issuer_present=0, completion_title_present=0,
certificate_structure_completeness=0.5` → **risk 0.7782, suspicious**.

## Controlled feature ablation (real model, one feature group at a time)

| Scenario | risk | verdict |
| --- | --- | --- |
| base | 0.778 | suspicious |
| + organization detected (trust 0.4) | **0.408** | **genuine** |
| + organization + known issuer (trust 1.0) | 0.405 | genuine |
| + organization + title | 0.331 | genuine |
| + title only | 0.757 | suspicious |
| + organization detected + title + QR | 0.380 | genuine |

**Responsible feature(s):** `issuer_present` / `organization_present` (and the
downstream `issuer_domain_trust`, which is 0 when the issuer is missing but 0.4
for any detected non-suspicious issuer). Merely detecting the issuer is enough
to cross the threshold; QR/signature/title are not the driver.

## Comparison with the two fixed Cisco certificates

| Case | org | course | title | risk | verdict |
| --- | --- | --- | --- | --- | --- |
| Introduction to Modern AI (Phase 10) | CISco | Machine Learning | Certificate of Course Completion | 0.267 | genuine |
| CCNA: Introduction to Networks | Chennai Institute of Technology | CCNA: Introduction to Networks | — | 0.305 | genuine |
| Python Essentials 1 (**before**) | (empty) | Python Essentials 1 | — | 0.778 | **suspicious** |
| Python Essentials 1 (**after**) | Cisco Networking Academy | Python Essentials 1 | — | 0.367 | **genuine** |

## Classification

**C. Issuer extraction failure.** Not OCR (OCR succeeded), not course/title
(extracted), not certificate-type (training detected correctly), not structural
(the structure features correctly encode "no issuer"), not visual (features
normal). The model is not at fault: it correctly assigns high risk when a
certificate's issuer cannot be recovered, and image-heavy certificates must
therefore rely on extraction recovering the issuer.

### Root cause

The OCR sentence `"...provided by Cisco Networking Academy in collaboration
with OpenEDG Python\nInstitute."` matched `ISSUER_MARKER_RE`; the capture was
`"Cisco Networking Academy in collaboration with OpenEDG Python"` — **61
characters**, exceeding the 60-char issuer cap in `_is_generic_issuer`, so the
whole organization was rejected as "generic" and the issuer was dropped.

## Fix (general-purpose, no certificate-specific bypass)

`backend/app/services/extraction_service.py`:

1. `ISSUER_CLAUSE_SPLIT_RE` now truncates issuer captures at affiliation
   clauses (`in collaboration/partnership/association/cooperation/conjunction
   with`). The issuing organization is the part **before** the clause, so the
   capture becomes `"Cisco Networking Academy"` (23 chars). Applies to any
   certificate phrased "provided by X in collaboration with Y".
2. `_clean_issuer_marker` additionally strips dangling prepositions at the end
   of a capture (e.g. an OCR line break leaving `"X in"`), which is common in
   image-heavy scans.

No model change, no threshold change, no retraining, no Cisco/Python-specific
rules, no whitelisting.

## Regression risk

- Clause splitting only ever shortens a marker capture at a recognizable
  affiliation phrase; issuer names without such a phrase are untouched
  (verified: `University of Cambridge` unchanged).
- All 4 existing fraud certs remain suspicious (0.99+); a fraud cert phrased
  "provided by Online Degree Emporium in collaboration with Instant Diploma
  Mill" still resolves issuer `Online Degree Emporium` → `issuer_domain_trust
  0.15` (suspicious-word match) and stays suspicious.
- Both Cisco certs and the genuine AWS cert keep their genuine verdicts.

## Regression tests (added)

`backend/tests/test_python_essentials_regression.py` (+7):

- `_extract_issuer` on the exact OCR text → `Cisco Networking Academy`
- clause-split variants (collaboration/partnership/association/cooperation/conjunction)
- non-clause issuer name unchanged
- full field extraction from the exact OCR text (name/issuer/course/date)
- real certificate fixture (image-heavy) → issuer recovered via OCR, hybrid method
- real certificate fixture via `/api/verify` → **genuine**, risk < 0.5
- fraud cert with an affiliation clause still suspicious

The real PDF lives at `backend/tests/fixtures/python_essentials.pdf` so the
OCR integration tests exercise the exact image the user uploaded.

## Invariants confirmed

- Model artifact SHA-256 `e402dca2…` unchanged; no model change, no retrain.
- Feature schema still 31 columns; decision threshold still 0.5.
- Backend suite: **219 passed** (212 before + 7 new). Frontend build passes.
- Missing fields still stay missing; no feature schema changes; OCR output
  still feeds no new ML features.