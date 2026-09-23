# Phase 9 — Feedback & Learning Loop

This document describes the human-review feedback loop added in Phase 9: how
review decisions are recorded, how the system surfaces out-of-distribution
(OOD) signals and review priorities, how feedback is analyzed, and how leakage-
safe candidate training datasets can be built from confirmed reviews.

**Important scope note:** Phase 9 does **not** retrain, replace, or promote any
model. The production model remains `random_forest_v3` (31 features, threshold
0.5). All artifacts produced here are **candidates / evidence** that a human
must explicitly promote using the existing training tooling.

---

## 1. Vocabulary

Three distinct concepts must not be conflated:

| Term | Meaning | Where it lives |
|---|---|---|
| AI prediction | The ML model's `prediction` / `risk_score` at verification time | immutable `Verification` record |
| Human review | A reviewer's `reviewer_label` after examining a certificate | immutable `VerificationFeedback` row |
| Ground truth | The true status of a certificate (unknown at runtime) | not stored; human review is the closest proxy |

The system never overwrites an AI prediction with a human review. Feedback is
stored **next to** the verification as evidence.

## 2. Reviewer Labels

| Label | Meaning | Used in candidate dataset? |
|---|---|---|
| `confirmed_genuine` | Reviewer verified the certificate as genuine | Yes |
| `confirmed_suspicious` | Reviewer verified the certificate as fraudulent/suspicious | Yes |
| `uncertain` | Reviewer could not decide | No |
| *(no feedback row)* | Not yet reviewed | No |

One decision per verification. Duplicate submissions are rejected (`400`) to
keep the audit trail unambiguous; updating a decision is intentionally
unsupported.

## 3. Workflow

```
upload → AI verification (prediction, intelligence, ood_status, review_priority)
  → Review Workbench lists unreviewed verifications (priority order)
  → reviewer expands a row: prediction, risk, signals, findings, duplicate info
  → reviewer submits confirmed_genuine / confirmed_suspicious / uncertain (+ note)
  → feedback row persisted (snapshot of the original prediction + metadata)
  → /api/feedback/summary and /api/feedback/analytics reflect the decision
  → (offline, explicit) build_candidate_dataset + benchmark → human promotes
```

## 4. Lifecycle of a verification

1. **Verification** — the ML model produces the prediction; the system also
   computes and persists:
   - `ood_status` (see §5)
   - `review_priority` (see §6)
   - `extraction_completeness` (fraction of identity fields extracted)
   - an `intelligence_json` snapshot including the 31 feature vector (so a
     candidate dataset can be built even without re-parsing the file)
2. **Review** — a human submits a decision; the feedback row snapshots the
   original prediction, risk score, confidence, model version, cert type,
   issuer, OOD status, priority, fingerprints, and `is_disagreement`.
3. **Candidate** — offline, confirmed reviews can be exported to a candidate
   dataset (see §9). `split` / `dataset_batch` are persisted back onto the
   feedback rows so the dataset can be traced to individual reviews.

## 5. Out-of-Distribution Signal (`ood_status`)

Advisory only — **never** a model feature and **never** treated as proof of fraud.

- `normal` — the certificate looks like the training distribution.
- `unusual` — unusual combinations or structural anomalies (e.g., academic +
  online flags together).
- `insufficient_information` — too little text/fields to judge.

Implemented in `app/services/ood_service.py::compute_ood_status`. The signal is
shown in the UI as an informational badge.

## 6. Review Priority (`review_priority`)

Triage for human reviewers, separate from the ML prediction and the Phase 8
`review_status`:

- `high` — high-risk prediction, duplicate reuse, high-severity consistency
  findings, or an `unusual` OOD status.
- `medium` — manual-review band, or insufficient information.
- `low` — otherwise.

Implemented in `app/services/priority_service.py::compute_review_priority`.
The Review Workbench sorts by priority so reviewers look at the most important
cases first.

## 7. Feedback Analytics

`GET /api/feedback/analytics` (implemented in `app/services/feedback_service.py`)
reports:

- **Summary** — reviewed counts per label, agreement/disagreement counts and
  rates.
- **Overall** — reviewer-vs-model confusion metrics treating
  `confirmed_genuine` as the positive class: precision/recall/F1, false-positive
  rate, false-negative rate, accuracy.
- **Per-group breakdowns** — by certificate type, issuer, review status,
  priority, and extraction-completeness bucket.
- **Averages / distributions** — average extraction completeness, OOD
  distribution, priority distribution, manual-review rate.

### Sample-size guards (no invented statistics)

- Overall percentage metrics require at least **10 decisive samples**
  (`MIN_METRIC_SAMPLES`).
- Per-group percentage metrics require at least **5 samples**
  (`MIN_GROUP_SAMPLES`).
- Below those thresholds a group reports `sufficient: false` and the percentage
  fields are **omitted** (not zero, not guessed).

## 8. Error Analysis

`src/feedback/analyze.py` produces a reviewer-vs-model breakdown to find
systematic error patterns (e.g., "high recall on suspicious, but several
false positives on completion certificates"). Same sample-size guards apply.

`scripts/analyze_feedback.py` is the CLI wrapper.

## 9. Candidate Dataset

`src/feedback/candidate_dataset.py::build_candidate_dataset` converts confirmed
reviews into a leakage-safe train/test CSV:

```
scripts/build_candidate_dataset.py --output data/reviewed [--test-fraction 0.20]
```

Rules enforced:

1. **Only confirmed labels qualify** — `uncertain` and unreviewed are excluded.
2. **Original metadata preserved** — verification id, prediction snapshot,
   reviewer label, certificate type, issuer, fingerprints, split, batch.
3. **Feature vectors** — taken from the persisted `intelligence_json` snapshot;
   falls back to recomputing from the stored file for legacy rows.
4. **Duplicate prevention** — rows sharing a file / cert-id / identity
   fingerprint are deduplicated (reported, not silent).
5. **Leakage-safe split** — `src/feedback/splitter.py` uses union-find to keep
   fingerprint families together; cross-split leakage is checked and
   **fails loudly** (`LeakageError`), never silently skipped.
6. **Frozen external-validation guard** — a reviewed example that matches a
   file in the frozen `external_validation/` set raises `LeakageError`.

Outputs: `<batch>.csv` + `<batch>_report.json` under `data/reviewed/`. The
report includes class balance, split counts, feature availability, leakage
checks, and duplicate report.

## 10. Benchmarking Reviewed Models

`src/feedback/benchmark.py` trains candidate models on the candidate dataset and
compares them (accuracy, precision, recall, F1, and priority-ranked error
patterns) against the frozen external validation set.

`scripts/benchmark_reviewed_models.py` is the CLI wrapper.

**No candidate is ever auto-promoted.** Promotion uses the existing explicit
training tooling (`python -m src.models.train_model`), and the frozen external
validation set remains the gatekeeper.

## 11. Quality Report

`src/feedback/quality_report.py::build_quality_report` summarizes candidate
dataset quality:

- class balance and rebalancing flag
- underrepresented certificate types / issuers
- cross-split fingerprint leakage counts (must be 0)
- duplicate counts per fingerprint type

`scripts/data_quality_report.py` is the CLI wrapper.

## 12. Limitations

- Reviewer labels are only as good as the reviewers; the analytics measure the
  **agreement between reviewer and model**, not absolute accuracy.
- Sample-size guards mean analytics may stay `insufficient` until enough
  decisive reviews accumulate.
- Candidate datasets contain only reviewed examples; until the review backlog
  is cleared the dataset may be small and class-imbalanced.
- The OOD signal is advisory and can never be used as evidence of fraud on its
  own.