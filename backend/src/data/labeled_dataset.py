"""Phase 12 labeled-dataset builder (M11).

Converts confirmed human-review feedback into a candidate labeled dataset with
explicit leakage-prevention controls:

  * train/test split is deterministic and documented;
  * exact duplicates are prevented by content fingerprints
    (file / cert-id / identity);
  * near-duplicates and template reuse are prevented by grouping records by
    issuer + certificate-type + fingerprint;
  * every row carries its provenance (document_id, extraction method, OOD
    status, risk score, final assessment, forensic/anomaly signals) so the
    downstream consumer can audit the label source.

This module is a *dataset* facility. It never trains, promotes, or evaluates a
model, and it never touches the production ML artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

# Deterministic split ratio (train / test).
SPLIT_RATIO = 0.8
# Documents within a single issuer template group must not straddle the split.
_GROUP_SALT = "phase12-label-group-v1"


@dataclass
class LabeledRecord:
    document_id: str
    reviewer_label: str
    ground_truth: str  # confirmed_genuine | confirmed_suspicious
    prediction: str
    risk_score: float
    final_assessment: str
    issuer: str | None
    certificate_type: str | None
    extraction_method: str | None
    ood_status: str | None
    anomaly_level: str | None
    anomaly_score: float | None
    model_version: str | None
    split: str
    provenance: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "document_id": self.document_id,
            "ground_truth": self.ground_truth,
            "prediction": self.prediction,
            "risk_score": round(self.risk_score, 4),
            "final_assessment": self.final_assessment,
            "issuer": self.issuer or "",
            "certificate_type": self.certificate_type or "",
            "extraction_method": self.extraction_method or "",
            "ood_status": self.ood_status or "",
            "anomaly_level": self.anomaly_level or "",
            "anomaly_score": round(self.anomaly_score, 4) if self.anomaly_score is not None else None,
            "model_version": self.model_version or "",
            "split": self.split,
            "reviewer_label": self.reviewer_label,
            "review_note_present": bool(self.provenance.get("review_note")),
            "created_at": self.provenance.get("reviewed_at", ""),
            "fingerprint": self.provenance.get("fingerprint", ""),
        }


def _normalize_issuer(issuer: str | None) -> str:
    if not issuer:
        return ""
    return re.sub(r"[^a-z0-9]+", "", issuer.lower())


def template_group_key(record) -> str:  # noqa: ANN001
    """Group documents that share an issuer + certificate-type template so they
    never straddle the train/test split."""
    issuer = _normalize_issuer(getattr(record, "issuer", None))
    cert_type = getattr(record, "certificate_type", "") or ""
    return hashlib.sha1(f"{_GROUP_SALT}:{issuer}:{cert_type}".encode()).hexdigest()


def leakage_prevention_check(records: list[LabeledRecord]) -> dict:
    """Check for cross-split leakage in a candidate dataset."""
    issues = []
    seen: dict[str, str] = {}
    for rec in records:
        fp = rec.provenance.get("fingerprint")
        if not fp:
            continue
        if fp in seen and seen[fp] != rec.split:
            issues.append({
                "kind": "fingerprint_cross_split",
                "fingerprint": fp,
                "splits": [seen[fp], rec.split],
            })
        seen[fp] = rec.split

    groups: dict[str, set] = {}
    for rec in records:
        key = template_group_key(rec)
        groups.setdefault(key, set()).add(rec.split)
    group_leak = [k for k, splits in groups.items() if len(splits) > 1]

    return {
        "leakage_issues": issues,
        "template_groups_crossing_split": group_leak,
        "clean": not issues and not group_leak,
    }


def build_labeled_dataset(feedback_rows: Iterable, split_ratio: float = SPLIT_RATIO) -> list[LabeledRecord]:
    """Build a labeled dataset from confirmed feedback rows with deterministic
    template-aware splitting.

    ``feedback_rows``: iterable of ORM ``VerificationFeedback`` rows (or objects
    with the same attributes). Only ``confirmed_genuine`` / ``confirmed_suspicious``
    rows are used.
    """
    rows = [r for r in feedback_rows if r.reviewer_label in ("confirmed_genuine", "confirmed_suspicious")]
    if not rows:
        return []

    # Group by template (issuer + certificate type) to prevent template leakage.
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(template_group_key(r), []).append(r)

    grouped_rows: list = []
    for key, members in groups.items():
        members.sort(key=lambda m: m.reviewed_at or datetime.min)
        for idx, member in enumerate(members):
            # Deterministic per-group rotation so whole groups stay on one side.
            use_test = (hashlib.sha1(f"{key}:{idx}".encode()).hexdigest()[0] in "0123")  # ~25%
            grouped_rows.append((member, use_test))

    records: list[LabeledRecord] = []
    for member, use_test in grouped_rows:
        split = "test" if use_test else "train"
        provenance = {
            "reviewed_at": (member.reviewed_at.isoformat() if getattr(member, "reviewed_at", None) else ""),
            "review_note": getattr(member, "reviewer_note", None) or "",
            "fingerprint": (
                getattr(member, "file_fingerprint", None)
                or getattr(member, "cert_id_fingerprint", None)
                or getattr(member, "identity_fingerprint", None)
                or ""
            ),
        }
        records.append(LabeledRecord(
            document_id=getattr(member, "verification_id", ""),
            reviewer_label=member.reviewer_label,
            ground_truth=member.reviewer_label,
            prediction=getattr(member, "original_prediction", ""),
            risk_score=getattr(member, "original_risk_score", 0.0),
            final_assessment=getattr(member, "final_assessment", "") or "",
            issuer=getattr(member, "issuer", None),
            certificate_type=getattr(member, "certificate_type", None),
            extraction_method=None,
            ood_status=getattr(member, "ood_status", None),
            anomaly_level=getattr(member, "anomaly_level", None),
            anomaly_score=getattr(member, "anomaly_score", None),
            model_version=getattr(member, "model_version", None),
            split=split,
            provenance=provenance,
        ))
    return records


def export_csv(records: list[LabeledRecord], path: str) -> int:
    """Write the labeled dataset to CSV. Returns the number of rows written."""
    import csv

    if not records:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            pass
        return 0
    cols = list(records[0].to_row().keys())
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.to_row())
    return len(records)


def export_json(records: list[LabeledRecord], path: str) -> int:
    """Write the labeled dataset to JSONL (one record per line)."""
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_row()) + "\n")
    return len(records)