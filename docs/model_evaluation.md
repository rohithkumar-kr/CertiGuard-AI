# Model Evaluation

## Active production model

- **Model:** `random_forest_v3` (scikit-learn Random Forest, `class_weight`
  balanced)
- **Features:** 31 (feature schema `v3`)
- **Decision threshold:** `0.5` on predicted fraud probability (risk score)
- **Served via:** `app/ml/model.py` → `src/inference/predict.py`

## Held-out test split (random_forest_v3, its own split, 800 rows)

| Metric | Value |
|---|---|
| Accuracy | 0.9287 |
| Precision | 0.9422 |
| Recall | 0.8281 |
| F1 | 0.8815 |
| Confusion matrix | `[[531, 13], [44, 212]]` |

## Frozen external validation (27 PDFs, never in training, real pipeline)

Run through the actual production pipeline (`scripts/run_generalization_validation.py`):

| Metric | Value |
|---|---|
| Samples | 27 |
| Accuracy | 0.963 |
| Genuine recall | 0.9286 |
| Suspicious recall | 1.0000 |
| False-positive rate | 0.0714 |
| False-negative rate | 0.0000 |
| False positives | 1 |
| False negatives | 0 |

Per-type coverage: academic(6), completion(5), online(4), technical(4),
training(4), workshop(4). All types except academic score 100% accuracy.

**Single false positive:** `academic/deshpande_501766.pdf` — an internally
inconsistent but genuine academic certificate (grade "B" alongside 91/100
marks). This is an expected pattern for an AI screening tool: genuinely
ambiguous documents get flagged for manual review rather than silently
accepted. This PDF is frozen and intentionally not "fixed".

**False negatives: 0.** No fraudulent document in the frozen set was missed.

## Decision history

| Phase | Candidate | Outcome | Evidence |
|---|---|---|---|
| 5B | v2 | superseded by v3 | v3 fixed 2 remaining technical FPs |
| 5C | v3 | **promoted (active)** | technical genuine recall 0%→100%, suspicious recall held at 100%, zero FNs |
| 6B | v4 (6-type dataset, workshop stratum) | **NOT promoted** | workshop ROC-AUC 0.8755→0.9457 but frozen external identical to v3 (acc 0.963, FP=1, FN=0) and overall test metrics identical |
| 6C | v4 calibrated (isotonic) | **NOT promoted** (candidate) | Brier 0.0697→0.0633 on held-out validation with zero prediction changes on the frozen set; no decision benefit |

Full details in `backend/monitoring/benchmark_report.json` and
`backend/monitoring/generalization_report*.json`.

## Threshold analysis (Phase 6C)

Threshold sweep on a held-out 600-row validation split (out-of-distribution for
v3):

| Threshold | Accuracy | Precision | Recall | F1 | FPR | FNR | #FP | #FN |
|---|---|---|---|---|---|---|---|---|
| 0.30 | 0.9200 | 0.9016 | 0.8462 | 0.8730 | 0.0444 | 0.1538 | 18 | 30 |
| 0.35 | 0.9317 | 0.9425 | 0.8410 | 0.8889 | 0.0247 | 0.1590 | 10 | 31 |
| 0.40 | 0.9300 | 0.9422 | 0.8359 | 0.8859 | 0.0247 | 0.1641 | 10 | 32 |
| 0.45 | 0.9300 | 0.9474 | 0.8308 | 0.8852 | 0.0222 | 0.1692 | 9 | 33 |
| **0.50** | **0.9300** | **0.9474** | **0.8308** | **0.8852** | **0.0222** | **0.1692** | 9 | 33 |
| 0.55 | 0.9317 | 0.9529 | 0.8308 | 0.8877 | 0.0198 | 0.1692 | 8 | 33 |
| 0.60 | 0.9317 | 0.9529 | 0.8308 | 0.8877 | 0.0198 | 0.1692 | 8 | 33 |

Lowering the threshold to 0.30 reduces false negatives by only 3 (33→30) while
**doubling** false positives (9→18) and cutting precision from 0.9474 to 0.9016.
Raising to 0.55/0.60 yields no gain. **0.5 is retained** as the decision
boundary.

## Calibration assessment (Phase 6C)

On the same 600-row validation split (calibration fit on the 2,596-row training
split only via 3-fold CV):

| Method | Brier | ROC-AUC | PR-AUC | Mean predicted prob |
|---|---|---|---|---|
| raw (active) | 0.0697 | 0.9261 | 0.9064 | 0.3848 |
| sigmoid | 0.0645 | 0.9185 | 0.9011 | 0.3341 |
| isotonic | 0.0633 | 0.9199 | 0.8956 | 0.3329 |

Actual validation fraud rate: 0.325. Calibration improves Brier (isotonic best)
at negligible AUC cost, and changes **zero** predictions on the frozen 27-doc
external set. Because it is not an accuracy improvement and would alter
risk-score/confidence semantics with no decision benefit, the production model
remains raw `random_forest_v3` at threshold 0.5. The calibrated candidate is
versioned as `random_forest_v4_calibrated` in `models/`.

## Genuine vs suspicious example results (live API)

| Document | Prediction | Risk score |
|---|---|---|
| `genuine_certificate.pdf` (University of Cambridge, consistent fields) | genuine | 0.2494 |
| `inconsistent_certificate.pdf` (marks/grade contradiction) | suspicious | 0.9867 |
| `aws_completion_certificate.pdf` (corporate completion) | genuine | 0.223 |
| `fraud_instant_cert.pdf` (instant-certificate sales wording) | suspicious | 0.997 |
| `deshpande_501766.pdf` (genuine but internally inconsistent) | suspicious | 0.542 |

## Review-status banding (Phase 8)

A three-level advisory status is layered on the **unchanged** ML risk score:
`low_risk`, `manual_review`, `high_risk`. It does not alter the prediction,
threshold, or risk score. Rules and constants are documented in
`docs/architecture.md` and unit-tested in `backend/tests/test_phase8.py`.

Example live results with review status (from the Phase 8 API smoke test):

| Document | Prediction | Risk score | Review status | Action |
|---|---|---|---|---|
| `genuine_certificate.pdf` (Cambridge, consistent) | genuine | 0.316 | manual_review (band ≥ 0.30) | manual review |
| `inconsistent_certificate.pdf` (marks/grade contradiction) | suspicious | 0.9867 | high_risk | investigate |
| `aws_completion_certificate.pdf` (corporate completion) | genuine | 0.223 | low_risk | accept |

The banding deliberately routes mid-range genuine documents (risk 0.30–0.50)
to manual review rather than silent acceptance — consistent with the tool's
"flag for review over silently accept" design.

## Important caveats

- All training data is **synthetic/prototype**. Real-world performance is a
  preliminary estimate, not a guarantee.
- Unusual / out-of-distribution certificate formats **can produce false
  positives** (genuine flagged suspicious) — by design the tool errs toward
  flagging for manual review rather than silently accepting.
- `manual_review` / `high_risk` are advisory bandings, not proof of fraud;
  `low_risk` is not proof of authenticity.
- These are **preliminary AI risk assessments, not legal authentication**.