"""Shared constants for the feedback / learning pipeline (Phase 9).

These mirror the runtime vocabulary in app/models/feedback.py so the API,
scripts, and tests stay consistent.
"""

REVIEWER_LABELS = ("confirmed_genuine", "confirmed_suspicious", "uncertain")
QUALIFYING_LABELS = ("confirmed_genuine", "confirmed_suspicious")
SPLIT_LABELS = ("train", "test")

# Minimum number of decisive samples before a percentage metric is reported.
MIN_METRIC_SAMPLES = 10
# Minimum samples in a sub-group (per certificate type / issuer / etc.).
MIN_GROUP_SAMPLES = 5

# Candidate dataset output directory (under backend/).
CANDIDATE_DATA_DIR = "data/reviewed"

# Default train/test split used by the candidate dataset builder.
DEFAULT_TEST_FRACTION = 0.20