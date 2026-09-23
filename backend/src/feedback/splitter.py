"""Deterministic, leakage-safe train/test split assignment (Phase 9D/9K).

Rows that share ANY fingerprint (file, certificate ID, identity, or the raw
certificate_id) form a connected component. Components are assigned wholly to
one split so that no certificate or identity can straddle the train/test
boundary. The assignment is deterministic (seeded) so re-running the builder
produces the same splits.
"""

from __future__ import annotations

import hashlib

import pandas as pd

_LINK_COLUMNS = ("file_fingerprint", "cert_id_fingerprint", "identity_fingerprint", "certificate_id")


def _component_id(row: pd.Series, index: int) -> str:
    """Deterministic canonical key for a single row."""
    parts = []
    for col in _LINK_COLUMNS:
        if col in row and row[col] is not None and str(row[col]).strip():
            parts.append(f"{col}={str(row[col]).strip()}")
    if not parts:
        parts.append(f"row={index}")
    return "|".join(sorted(parts))


def assign_splits(
    df: pd.DataFrame, test_fraction: float = 0.20, seed: int = 42
) -> pd.DataFrame:
    """Add a 'split' column assigning each row to 'train' or 'test'.

    The split is decided at the connected-component level so duplicates never
    straddle the boundary. Components are sorted by (size, canonical id) and
    greedily assigned to keep the test fraction as close to ``test_fraction``
    as possible without splitting a component.
    """
    if df.empty:
        return df.copy()

    # Build components via union-find over rows that share any link value.
    value_to_row: dict[str, list[int]] = {}
    for idx, (_, row) in enumerate(df.iterrows()):
        for col in _LINK_COLUMNS:
            if col in df.columns and row.get(col) is not None and str(row.get(col)).strip():
                key = f"{col}={str(row.get(col)).strip()}"
                value_to_row.setdefault(key, []).append(idx)

    parent = list(range(len(df)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for members in value_to_row.values():
        first = members[0]
        for other in members[1:]:
            union(first, other)

    components: dict[int, list[int]] = {}
    for i in range(len(df)):
        components.setdefault(find(i), []).append(i)

    comp_sizes = [(len(members), members) for members in components.values()]

    def component_seed(members: list[int]) -> int:
        canonical = _component_id(df.iloc[members[0]], members[0])
        digest = hashlib.sha256(f"{seed}:{canonical}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    # Deterministic ordering: by size desc, then by seeded key.
    ordered = sorted(
        comp_sizes,
        key=lambda t: (-t[0], component_seed(t[1]), t[1][0]),
    )

    target_test = int(round(len(df) * test_fraction))
    split = ["train"] * len(df)
    assigned_test = 0
    for size, members in ordered:
        if assigned_test + size <= target_test:
            for m in members:
                split[m] = "test"
            assigned_test += size

    out = df.copy()
    out["split"] = split
    return out