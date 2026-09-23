# Phase 12 Completion Report — Universal Certificate Evidence Engine

## 1. Summary

Phase 12 adds a deterministic, multi-layer **evidence engine** that runs around
the existing ML verdict and produces a transparent final assessment:

`LIKELY_GENUINE | LIKELY_SUSPICIOUS | REQUIRES_VERIFICATION | INSUFFICIENT_EVIDENCE`

Every category of evidence is independent, every fusion decision is encoded as
an explicit, unit-tested rule, and the ML model, its 31-feature schema, its 0.5
threshold, and its artifact bytes are **untouched**.

## 2. Deliverables (M1–M16)

| Milestone | Deliverable | Status |
| --- | --- | --- |
| M1 | `app/services/pdf_forensics.py` — PDF structural analysis | Done |
| M2 | `app/services/visual_analysis.py` + `tampering_service.py` (OpenCV 5.0.0 headless) | Done |
| M3 | `app/services/qr_service.py` — QR detection / decode / verification-page | Done |
| M4 | `app/services/issuer/` — registry, adapters, `issuer_registry.json` | Done |
| M5 | `app/services/semantic_service.py` — plausibility + OOD | Done |
| M6 | `app/services/anomaly_service.py` — aggregate anomaly engine | Done |
| M7 | `app/services/evidence_fusion.py` — decision tree | Done |
| M8 | `app/ml/model_registry.py` — frozen-artifact integrity guard | Done |
| M9 | `phase12_pipeline.py` + integration (verification service, model, DB, schemas, routes) | Done |
| M10 | Frontend evidence UI (`EvidencePanel` in ResultCard + ReviewWorkbench) | Done |
| M11 | Feedback columns (`final_assessment`, `anomaly_score`, `anomaly_level`) + snapshot + `src/data/labeled_dataset.py` | Done |
| M12 | `tests/test_phase12_regression_set.py` (known-difficult set) | Done |
| M13 | `scripts/run_phase12_validation.py` + `scripts/generate_phase12_report.py` + `monitoring/phase12_report.json` | Done |
| M14 | `tests/test_phase12_model_integrity.py` | Done |
| M15 | Docs: forensics / fusion / issuer / tampering (new) + architecture / ml_pipeline / api / README (updated) | Done |
| M16 | Full test run + frontend typecheck/build + report | Done |

## 3. Evidence categories

| Category | Source | Invariants |
| --- | --- | --- |
| `ml` | `model_registry.py` + risk score | High risk = evidence, not proof |
| `extraction` | Phase 10 metadata | Missing fields ≠ fake; OCR failure ≠ fake |
| `structure` | extraction/intelligence | Missing structure ≠ fake |
| `semantic` | `semantic_service.py` | OOD ≠ fake |
| `forensics` | `pdf_forensics.py` | Malformed ≠ fake (→ INSUFFICIENT_EVIDENCE) |
| `visual` | `visual_analysis.py` | Image-only ≠ fake |
| `tampering` | `tampering_service.py` | Strong tampering raises suspicion |
| `qr` | `qr_service.py` | QR absence ≠ fake; existence ≠ authenticity |
| `issuer` | `issuer/` registry | Unknown issuer ≠ fake; blocklist = high-severity FAIL |
| `anomaly` | `anomaly_service.py` | Single weak signal never dominates |
| `external` | config-gated | Disabled by default; unknown QR domain ≠ fraud |
| `duplicate` | Phase 8 fingerprints | File dup → REQUIRES_VERIFICATION; cert_id dup → LIKELY_SUSPICIOUS |

Fusion rules are enumerated in `docs/evidence_fusion.md` and unit-tested in
`tests/test_phase12_evidence.py` (21 tests), including: clean genuine →
`LIKELY_GENUINE`; insufficient → `INSUFFICIENT_EVIDENCE`; fraud multi-FAIL →
`LIKELY_SUSPICIOUS`; strong tampering → `LIKELY_SUSPICIOUS`; ML-suspicious +
clean structure → `REQUIRES_VERIFICATION`; external-verified + ML-suspicious →
`REQUIRES_VERIFICATION`; file-duplicate genuine → `REQUIRES_VERIFICATION`.

## 4. Validation results

`scripts/run_phase12_validation.py` verifies the **frozen external-validation
corpus (27 documents)** plus the **known-difficult regression set (3)** —
30 documents total, with ground truth from the manifest. It uses a dedicated
database and never touches dev data.

| Metric | ML model | Evidence engine |
| --- | --- | --- |
| Decisive samples | 21 | 21 |
| Accuracy | 1.0000 | 1.0000 |
| Precision | 1.0000 | 1.0000 |
| Recall | 1.0000 | 1.0000 |
| F1 | 1.0000 | 1.0000 |
| False-positive rate | 0.0000 | 0.0000 |
| False-negative rate | 0.0000 | 0.0000 |
| FPs / FNs | 0 / 0 | 0 / 0 |

Assessment distribution over all 30 reviewed documents:

| Assessment | Count |
| --- | --- |
| `LIKELY_GENUINE` | 12 |
| `REQUIRES_VERIFICATION` | 7 |
| `LIKELY_SUSPICIOUS` | 9 |
| `INSUFFICIENT_EVIDENCE` | 2 |

Notable routing decisions:

- `deshpande_501766.pdf` (genuine, but the frozen model emits risk **0.542** —
  a pre-existing false positive): the evidence engine routes it to
  `REQUIRES_VERIFICATION` (human review) instead of `LIKELY_SUSPICIOUS`,
  exactly the intended conservative behavior for a single elevated signal.
- `fraud_empty_completion.pdf` / `fraud_blank_attendance.pdf` (blank fraud
  documents): `INSUFFICIENT_EVIDENCE` — insufficient extractable evidence, no
  confident verdict, sent to review.
- All 27 external-corpus documents keep their ML prediction; none of the 4
  fraud certs (risk ≥ 0.94) nor the 3 known-difficult genuine certs
  (risk ≤ 0.367) regressed.

Full numbers: `backend/monitoring/phase12_report.json`.

## 5. Model-integrity enforcement

`tests/test_phase12_model_integrity.py` (9 tests) asserts the artifacts and the
prediction contract are unchanged:

- Artifact SHA-256 `e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337`
- 31-feature schema, 0.5 threshold, feature-names list
- `prediction`/`risk_score`/`review_status` backward compatibility
- A canonical fraud document still predicts `suspicious` at ≥ 0.5

## 6. Test suite & build

- Backend: **259 passed** (`python -m pytest tests -q` from `backend`),
  including `test_phase12_evidence.py` (21), `test_phase12_model_integrity.py`
  (9), and `test_phase12_regression_set.py` (10).
- Frontend: `npm run typecheck` and `npm run build` both clean (43 modules,
  built in 601 ms).

## 7. Backward compatibility

- `prediction`, `label`, `risk_score`, `confidence`, `review_status`,
  `recommended_action`, signals, `duplicate`, `ood_status`, and the Phase 10
  `extraction` block are byte-for-byte unchanged.
- Phase 12 adds `verification_evidence` to the response and the
  `evidence_details` snapshot on the detail endpoint; both are additive.
- `evidence_json` (verifications) and the Phase 11 feedback columns are added
  by idempotent migrations.

## 8. Constraint-compliance checklist

- No retraining, no promotion, no runtime training code. ✅
- Model artifact, 31-feature schema, 0.5 threshold untouched (integrity-tested). ✅
- No certificate/company-specific rules or whitelists in the pipeline. ✅
- `issuer_known` / `issuer_domain_trust` ML features sourced exactly as before
  (issuer layer is advisory only). ✅
- `EXTERNAL_VERIFY_ENABLED=false` by default; bounded timeouts/responses. ✅
- No legal-authenticity claims; disclaimer retained in UI. ✅

## 9. Known limitations

- Tampering detection is heuristic and best-effort; heavy legitimate
  re-compression can produce artifacts.
- External verification is disabled by default and is not required for any
  verdict.
- The evidence engine inherits the frozen model's risk score; it adds a
  conservative routing layer, not a new predictor.
- Validation ground truth comes from the synthetic manifest; real-world
  certificates should continue to be routed to manual review for
  high-stakes decisions.

## 10. Artifacts

- Reports: `backend/monitoring/phase12_report.json`
- Docs: `docs/universal_certificate_forensics.md`, `docs/evidence_fusion.md`,
  `docs/issuer_verification.md`, `docs/tampering_detection.md`
- Tests: `backend/tests/test_phase12_evidence.py`,
  `test_phase12_model_integrity.py`, `test_phase12_regression_set.py`
- Scripts: `backend/scripts/run_phase12_validation.py`,
  `backend/scripts/generate_phase12_report.py`