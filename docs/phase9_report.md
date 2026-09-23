# Phase 9 Completion Report — Feedback & Learning Loop

**Status:** Complete
**Scope:** Real-world feedback collection, OOD/priority advisory signals, review
workbench, feedback analytics, and leakage-safe candidate dataset tooling.
**Hard constraint honored:** the production model was **not** retrained,
replaced, or promoted. `random_forest_v3`, 31 features, threshold 0.5, and the
frozen external validation set are unchanged.

---

## 1. What was built

### Runtime (FastAPI)
- `GET /api/verifications/{id}` — full verification detail incl. persisted
  intelligence snapshot and any review decision (9H).
- `POST /api/verifications/{id}/feedback` — record a human decision
  (`confirmed_genuine` / `confirmed_suspicious` / `uncertain`) with note.
  Duplicate submissions rejected; feedback never alters prediction/risk (9B).
- `GET /api/feedback/summary` — reviewed counts, agreement/disagreement rates (9B).
- `GET /api/feedback/analytics` — reviewer-vs-model metrics with sample-size
  guards (`MIN_METRIC_SAMPLES=10`, `MIN_GROUP_SAMPLES=5`); below threshold the
  percentages are omitted, never invented (9I).
- `ood_status` (`normal | unusual | insufficient_information`) computed by
  `app/services/ood_service.py` and persisted — advisory only, not a feature
  (9F).
- `review_priority` (`low | medium | high`) computed by
  `app/services/priority_service.py` — triage separate from prediction (9G).
- `VerificationFeedback` ORM model + `Verification` columns
  (`ood_status`, `review_priority`, `intelligence_json`) with idempotent,
  additive DB migrations (9A).
- Verification now persists an `intelligence_json` snapshot that includes the
  31-feature vector, enabling candidate datasets without re-parsing files.

### Offline pipeline (`src/feedback/` + `scripts/`)
- `labels.py` — shared reviewer/split vocabulary.
- `splitter.py` — union-find leakage-safe train/test assignment (9K).
- `leakage.py` — cross-split + frozen-external-validation checks that
  **fail loudly** (`LeakageError`).
- `candidate_dataset.py` — builds leakage-safe candidate CSV + report, dedupes
  duplicate samples, persists split/batch back to feedback rows (9D).
- `analyze.py` — reviewer-vs-model error analysis with sample-size guards (9C).
- `quality_report.py` — class balance, underrepresented categories, leakage
  counts (9E).
- `benchmark.py` — candidate model comparison on the candidate dataset (9J);
  never auto-promotes.
- CLI wrappers: `analyze_feedback.py`, `data_quality_report.py`,
  `build_candidate_dataset.py`, `benchmark_reviewed_models.py`.

### Frontend
- Review Workbench view (toggle in the header) with priority-ordered reviewable
  list, expandable detail (signals/findings/duplicate/OOD/priority), three
  feedback actions, disable-after-submit, and an analytics block.
- `ResultCard` now shows OOD + review-priority badges.
- Types and API service extended for the new endpoints.

### Docs & tests
- `docs/api.md`, `README.md` updated; new `docs/feedback_learning.md`.
- **186 tests pass** (156 Phase 1–8 + 30 new Phase 9): feedback validation,
  duplicate submission, disagreement tracking, OOD, priority, detail endpoint,
  candidate dataset (dedupe + leakage), error analysis, quality report,
  analytics guards, leakage loud-failures.

## 2. Sample-size guard example

With 0–9 decisive reviews, `overall.sufficient` is `false` and
`false_positive_rate` / `accuracy` etc. are **omitted**; they appear only from
10+ decisive samples. Verified by tests and by running the CLI scripts against
the empty dev database.

## 3. Verification of the no-change guarantee

Final production safety check (9M):

| Item | Value |
|---|---|
| Model version | `random_forest_v3` |
| Feature count | 31 |
| Decision threshold | 0.5 |
| Artifact SHA-256 | `e402dca299d240323343dcbc48d12ee304ab26dd24ae15a8408e36149d74c337` (unchanged) |

The frozen 27-PDF external validation set was never modified.

## 4. Current dev database state

- `verifications` includes `ood_status`, `review_priority`, `intelligence_json`.
- `verification_feedback` table created with the full snapshot schema.
- Migrations were additive and already applied to the dev DB.

## 5. Known limitations

- No reviews have been collected yet, so analytics currently report
  "insufficient samples" — expected until reviewers use the workbench.
- Reviewer labels measure agreement between reviewer and model, not absolute
  ground truth.
- Candidate datasets only contain reviewed examples; keep the review backlog
  cleared to grow them.