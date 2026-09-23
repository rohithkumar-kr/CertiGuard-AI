"""Offline feedback / learning pipeline (Phase 9).

Modules:
  - analyze:           model error analysis over reviewed certificates (9C)
  - candidate_dataset: candidate training dataset builder (9D)
  - quality_report:    dataset quality report (9E)
  - benchmark:         future model benchmark pipeline (9J)
  - leakage:           leakage protection (9K)
  - splitter:          leakage-safe train/test split assignment (9D/9K)
  - labels:            shared constants

None of these modules trains or promotes a production model.
"""