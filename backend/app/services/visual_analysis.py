"""Visual / layout analysis (Phase 12, M2).

Region-level and layout-level analysis of a rendered certificate page:

  - per-region ink coverage / sharpness variance
  - edge-orientation consistency (alignment anomalies)
  - typography consistency (distinct text-blob heights)
  - duplicated-region detection (self-similarity)
  - blank / suspicious regions
  - compression-artifact proxy (noise texture)

This layer produces *evidence signals* only. Differences in fonts, colors,
presence of a seal/signature, or an image-only layout are NOT treated as
fraud. The four ML visual features (blank ratio, sharpness, noise, color
anomaly) are computed separately in ``extraction_service.compute_visual`` and
are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy.ndimage import label
from scipy.signal import convolve2d

_GRID = 4  # 4x4 grid of regions


@dataclass
class VisualReport:
    signals: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)


def _cell_stats(gray: np.ndarray, rows: int, cols: int) -> list[dict]:
    h, w = gray.shape
    rh, rw = h // rows, w // cols
    cells = []
    for r in range(rows):
        for c in range(cols):
            cell = gray[r * rh:(r + 1) * rh, c * rw:(c + 1) * rw]
            if cell.size == 0:
                cells.append({"ink": 0.0, "sharp": 0.0, "noise": 0.0})
                continue
            ink = float(np.mean(cell < 60))
            lap = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
            lap_img = convolve2d(cell, lap, mode="same", boundary="symm")
            sharp = float(np.clip(np.var(lap_img) / 400.0, 0.0, 1.0))
            cells.append({"ink": round(ink, 4), "sharp": round(sharp, 4)})
    return cells


def _edge_orientation_consistency(gray: np.ndarray) -> float:
    """Fraction of strong edges that are near-horizontal/vertical. 1.0 means a
    mostly axis-aligned layout (typical of structured certificates); low values
    suggest unusual rotation/skew or heavy decoration."""
    gy = convolve2d(gray, np.array([[1], [0], [-1]], dtype=np.float32), mode="same", boundary="symm")
    gx = convolve2d(gray, np.array([[1, 0, -1]], dtype=np.float32), mode="same", boundary="symm")
    mag = np.hypot(gx, gy)
    threshold = np.percentile(mag, 90)
    strong = mag > threshold
    if not strong.any():
        return 1.0
    angles = np.arctan2(gy[strong], gx[strong]) * 180.0 / np.pi
    aligned = (np.abs(angles) < 15) | (np.abs(angles - 90) < 15) | (np.abs(angles + 90) < 15) | (np.abs(angles - 180) < 15)
    return round(float(aligned.mean()), 4)


def _typography_clusters(gray: np.ndarray) -> int:
    """Approximate the number of distinct text-height clusters via connected
    components. A certificate with consistent typography yields few clusters;
    heavy mixing of fonts/sizes yields many."""
    binary = gray < 160
    lbl, n = label(binary)
    if n == 0:
        return 0
    heights = []
    for i in range(1, min(n + 1, 5000)):
        ys, _ = np.where(lbl == i)
        if ys.size < 8 or ys.size > 20000:
            continue
        heights.append(int(ys.max() - ys.min() + 1))
    if not heights:
        return 0
    # Cluster heights into bins (quantized to 2px).
    bins = {}
    for h in heights:
        bins.setdefault(h // 2, 0)
        bins[h // 2] += 1
    counts = sorted(bins.values(), reverse=True)
    total = sum(counts)
    major = sum(c for c in counts if c >= max(3, total * 0.02))
    return int(len(counts)) if major < 3 else int(len([c for c in counts if c >= max(3, total * 0.02)]) + min(3, len(counts) - major))


def _duplicated_regions(gray: np.ndarray) -> list[tuple]:
    """Find pairs of grid cells whose ink layout is near-identical, which can
    indicate a copied/pasted region. Advisory only."""
    rows = cols = _GRID
    h, w = gray.shape
    rh, rw = h // rows, w // cols
    cells = []
    for r in range(rows):
        for c in range(cols):
            cell = gray[r * rh:(r + 1) * rh, c * rw:(c + 1) * rw]
            bin_cell = (cell < 140).astype(np.float32)
            cells.append((r, c, bin_cell))
    pairs = []
    for i in range(len(cells)):
        for j in range(i + 1, len(cells)):
            ri, ci, a = cells[i]
            rj, cj, b = cells[j]
            # Skip neighbors: adjacent cells often share layout by design.
            if abs(ri - rj) + abs(ci - cj) == 1:
                continue
            if a.size == 0 or b.size == 0:
                continue
            inter = np.logical_and(a, b).sum()
            union = np.logical_or(a, b).sum()
            if union == 0:
                continue
            iou = inter / union
            if iou > 0.85:
                pairs.append(((ri, ci), (rj, cj), round(float(iou), 3)))
    return pairs


def analyze_visual(image: Image.Image) -> VisualReport:
    """Analyze a rendered certificate page (first page)."""
    report = VisualReport()
    signals = report.signals
    try:
        img = image.convert("RGB")
        img.thumbnail((1200, 1200))
        gray = np.asarray(img.convert("L"), dtype=np.float32)
        if gray.size == 0:
            signals["error"] = "empty image"
            report.anomalies.append({
                "key": "visual_unable", "label": "Visual analysis unavailable",
                "severity": "medium",
                "detail": "The rendered page was empty, so visual analysis could not run.",
            })
            return report

        cells = _cell_stats(gray, _GRID, _GRID)
        inks = [c["ink"] for c in cells]
        sharps = [c["sharp"] for c in cells]

        signals["region_ink_mean"] = round(float(np.mean(inks)), 4)
        signals["region_ink_std"] = round(float(np.std(inks)), 4)
        signals["region_sharpness_mean"] = round(float(np.mean(sharps)), 4)
        signals["region_sharpness_std"] = round(float(np.std(sharps)), 4)
        signals["edge_alignment_consistency"] = _edge_orientation_consistency(gray)
        signals["typography_cluster_count"] = _typography_clusters(gray)
        signals["blank_region_count"] = sum(1 for c in cells if c["ink"] < 0.005)
        signals["ink_heavy_region_count"] = sum(1 for c in cells if c["ink"] > 0.35)

        dup = _duplicated_regions(gray)
        signals["duplicated_region_pairs"] = dup
        signals["duplicated_region_count"] = len(dup)

        # Advisory anomaly flags (evidence only).
        if signals["region_ink_std"] > 0.12:
            report.anomalies.append({
                "key": "layout_inconsistency", "label": "Uneven ink distribution",
                "severity": "low",
                "detail": f"Region ink coverage is highly uneven (std={signals['region_ink_std']}).",
            })
        if signals["edge_alignment_consistency"] < 0.65:
            report.anomalies.append({
                "key": "alignment_anomaly", "label": "Unusual text alignment",
                "severity": "medium",
                "detail": f"Only {signals['edge_alignment_consistency']:.0%} of edges are "
                          "axis-aligned, which can indicate rotated or unusual layout.",
            })
        if signals["typography_cluster_count"] >= 8:
            report.anomalies.append({
                "key": "typography_inconsistency", "label": "Mixed typography",
                "severity": "low",
                "detail": f"{signals['typography_cluster_count']} distinct text-height "
                          "clusters detected; typography appears inconsistent.",
            })
        if dup:
            report.anomalies.append({
                "key": "duplicated_region", "label": "Duplicated visual region",
                "severity": "medium",
                "detail": f"{len(dup)} region pair(s) are near-identical, which can "
                          "indicate a copied/pasted area.",
            })
        if signals["ink_heavy_region_count"] > 0:
            report.anomalies.append({
                "key": "heavy_region", "label": "Unusually dense region",
                "severity": "low",
                "detail": f"{signals['ink_heavy_region_count']} region(s) are unusually "
                          "ink-dense.",
            })
    except Exception as exc:  # noqa: BLE001 - visual analysis must never raise
        signals["error"] = str(exc)
        report.anomalies.append({
            "key": "visual_error", "label": "Visual analysis error",
            "severity": "medium",
            "detail": f"Visual analysis failed: {exc}",
        })
    return report