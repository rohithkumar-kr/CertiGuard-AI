"""PDF forensics (Phase 12, M1).

Generic, issuer-independent analysis of a PDF's physical structure:

  - metadata / producer / creator / creation + modification timestamps
  - page count and dimensions (uniformity)
  - embedded fonts (count, types, embedding status)
  - embedded images (count, resolution, compression filters)
  - text / vector object density
  - annotations and hyperlinks
  - XMP metadata
  - xref structure, incremental-update indicators, encryption, repair state

Output is a structured ``ForensicReport`` of *evidence signals*. A metadata
anomaly is evidence, never a fraud verdict: unusual production software,
missing timestamps, or incremental updates are all consistent with legitimate
documents and MUST NOT be treated as proof of forgery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None  # type: ignore

_EOF_MARKER = b"%%EOF"


@dataclass
class ForensicReport:
    signals: dict = field(default_factory=dict)
    anomalies: list = field(default_factory=list)


def _parse_pdf_date(value: str | None) -> str | None:
    """Normalize a PDF date (D:YYYYMMDDHHmmSS... ) to ISO or None."""
    if not value:
        return None
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", value)
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = [int(g) if g else (1 if i == 1 else 0)
                              for i, g in enumerate([m.group(1), m.group(2), m.group(3),
                                                     m.group(4), m.group(5), m.group(6)])]
        if mo > 12 or d > 31:
            return None
        dt = datetime(y, mo, d, h, mi, s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _count_marker(data: bytes, marker: bytes) -> int:
    return data.count(marker)


def analyze_pdf(path: str, raw: bytes | None = None) -> ForensicReport:
    """Analyze the physical structure of a PDF file.

    ``raw`` (the uploaded bytes) is optional but improves incremental-update
    detection. All findings are advisory.
    """
    report = ForensicReport()
    signals = report.signals

    try:
        doc = fitz.open(path)
    except Exception as exc:  # noqa: BLE001 - forensics must never raise
        report.signals["error"] = str(exc)
        report.anomalies.append({
            "key": "pdf_open_failed",
            "label": "PDF could not be parsed",
            "severity": "high",
            "detail": f"PyMuPDF failed to open the document: {exc}",
        })
        return report

    try:
        md = doc.metadata or {}
        signals["metadata"] = {
            "format": md.get("format"),
            "title": md.get("title") or None,
            "author": md.get("author") or None,
            "subject": md.get("subject") or None,
            "keywords": md.get("keywords") or None,
            "creator": md.get("creator") or None,
            "producer": md.get("producer") or None,
            "creation_date": _parse_pdf_date(md.get("creationDate")),
            "modification_date": _parse_pdf_date(md.get("modDate")),
        }

        signals["page_count"] = len(doc)
        dims = []
        for page in doc:
            r = page.rect
            dims.append((round(r.width, 2), round(r.height, 2)))
        signals["page_dimensions"] = dims[0] if dims else None
        signals["page_dimensions_uniform"] = len(set(dims)) <= 1

        # --- Fonts ---
        fonts: list[dict] = []
        seen = set()
        for page in doc:
            for f in page.get_fonts(full=True):
                key = (f[1], f[3])
                if key in seen:
                    continue
                seen.add(key)
                fonts.append({
                    "type": f[2],
                    "basefont": f[3],
                    "embedded": bool(f[4]) if len(f) > 4 else True,
                })
        signals["font_count"] = len(fonts)
        signals["fonts"] = fonts[:20]
        signals["fonts_unembedded"] = [f["basefont"] for f in fonts if not f["embedded"]][:10]
        font_families = sorted({f["basefont"].split("+")[-1] for f in fonts if f["basefont"]})
        signals["font_families"] = font_families
        signals["font_consistency"] = "consistent" if len(font_families) <= 3 else "mixed"

        # --- Text/image overlay mix (advisory) ---
        # Real certificates often layer text over a logo/background; a page
        # where virtually every text block sits on top of a raster image may
        # indicate pasted text over an image. Advisory signal only.
        overlay_text_blocks = 0
        total_text_blocks = 0
        page_has_image = False
        page_has_text = False
        for page in doc:
            blocks = [b for b in page.get_text("blocks") if b[6] == 0]
            image_rects = []
            for img in page.get_images(full=True):
                image_rects.extend(page.get_image_rects(img[0]))
            total_text_blocks += len(blocks)
            page_has_image = page_has_image or bool(image_rects)
            page_has_text = page_has_text or bool(blocks)
            for b in blocks:
                from pymupdf import Rect
                br = Rect(b[:4])
                if any(br.intersects(ir) for ir in image_rects):
                    overlay_text_blocks += 1
        signals["text_image_overlap"] = {
            "page_has_text": page_has_text,
            "page_has_image": page_has_image,
            "overlay_text_blocks": overlay_text_blocks,
            "total_text_blocks": total_text_blocks,
            "overlay_ratio": round(overlay_text_blocks / total_text_blocks, 3) if total_text_blocks else 0.0,
        }
        signals["text_image_mix"] = bool(page_has_text and page_has_image)

        # --- Images ---
        image_info = []
        seen_imgs = set()
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen_imgs:
                    continue
                seen_imgs.add(xref)
                try:
                    pix = fitz.Pixmap(doc, xref)
                    w, h = pix.width, pix.height
                    comp = "raw"
                    try:
                        stream = doc.xref_stream(xref) or b""
                        sm = doc.xref_stream_raw(xref) or b""
                        if sm and sm != stream:
                            filters = re.findall(rb"/Filter\s*/(\w+)", doc.xref_object(xref).encode())
                            comp = ",".join(f.decode() for f in filters) if filters else "stream"
                        else:
                            comp = "raw"
                    except Exception:  # noqa: BLE001
                        comp = "unknown"
                    image_info.append({"xref": xref, "w": w, "h": h, "compression": comp})
                except Exception:  # noqa: BLE001
                    image_info.append({"xref": xref, "w": 0, "h": 0, "compression": "unknown"})
        signals["image_count"] = len(image_info)
        signals["images"] = image_info[:20]
        signals["image_compressions"] = sorted({i["compression"] for i in image_info})
        signals["image_resolutions"] = [(i["w"], i["h"]) for i in image_info if i["w"]][:20]
        signals["image_only_page"] = bool(image_info) and not bool(doc[0].get_text("text").strip())

        # --- Text / vector / annotation / link density ---
        text_blocks = 0
        drawings = 0
        annots = 0
        links = 0
        for page in doc:
            text_blocks += len(page.get_text("blocks"))
            drawings += len(page.get_drawings())
            if page.annots():
                annots += len(list(page.annots()))
            links += len(page.get_links())
        signals["text_object_count"] = text_blocks
        signals["vector_object_count"] = drawings
        signals["annotation_count"] = annots
        signals["link_count"] = links

        # --- XMP ---
        xmp = doc.get_xml_metadata()
        signals["xmp_present"] = bool(xmp and xmp.strip())
        signals["xmp_preview"] = (xmp[:200] if xmp else "")

        # --- Structure / xref ---
        signals["xref_length"] = doc.xref_length()
        signals["encrypted"] = bool(doc.is_encrypted)
        signals["needs_password"] = bool(doc.needs_pass)
        signals["repaired"] = bool(doc.is_repaired)
        signals["has_acroform"] = bool(doc.is_form_pdf)
        signals["pdf_version"] = doc.pdf_version if hasattr(doc, "pdf_version") else None
    finally:
        doc.close()

    # --- Incremental-update detection from raw bytes ---
    eof_count = _count_marker(raw or b"", _EOF_MARKER)
    signals["eof_marker_count"] = eof_count
    signals["incremental_update"] = eof_count > 1

    _collect_anomalies(report)
    return report


def _collect_anomalies(report: ForensicReport) -> None:
    """Turn evidence signals into advisory anomaly flags (never a verdict)."""
    signals = report.signals
    anomalies = report.anomalies
    md = signals.get("metadata") or {}
    # Never flag a document merely because metadata looks unusual.

    if signals.get("encrypted") or signals.get("needs_password"):
        anomalies.append({
            "key": "pdf_encrypted",
            "label": "Encrypted PDF",
            "severity": "medium",
            "detail": "The PDF is encrypted; this is unusual for a certificate but "
                      "not evidence of fraud.",
        })
    if signals.get("repaired"):
        anomalies.append({
            "key": "pdf_repaired",
            "label": "PDF required repair",
            "severity": "medium",
            "detail": "The PDF structure was damaged and had to be repaired by the parser.",
        })
    if signals.get("incremental_update"):
        anomalies.append({
            "key": "incremental_update",
            "label": "Incremental PDF update",
            "severity": "low",
            "detail": "The file contains multiple %%EOF markers, suggesting incremental "
                      "updates were appended. Evidence only.",
        })
    c_date = md.get("creation_date")
    m_date = md.get("modification_date")
    if c_date and m_date and c_date > m_date:
        anomalies.append({
            "key": "metadata_date_inconsistent",
            "label": "Metadata timestamp inconsistency",
            "severity": "medium",
            "detail": f"Creation time ({c_date}) is after the modification time ({m_date}).",
        })
    if c_date:
        try:
            if datetime.strptime(c_date, "%Y-%m-%d %H:%M:%S").year > 2100:
                anomalies.append({
                    "key": "metadata_future_date",
                    "label": "Future metadata timestamp",
                    "severity": "low",
                    "detail": f"Metadata creation time ({c_date}) is implausibly far in the future.",
                })
        except ValueError:
            pass
    # A pure-image page with metadata claiming a text word-processor producer
    # is an advisory mismatch, not proof of anything.
    if signals.get("image_only_page") and md.get("producer"):
        anomalies.append({
            "key": "scan_with_text_producer",
            "label": "Scanned page with text-tool metadata",
            "severity": "low",
            "detail": f"The page is image-only but the metadata producer is '{md['producer']}'.",
        })
    if len(signals.get("font_families") or []) > 8:
        anomalies.append({
            "key": "unusual_font_mix",
            "label": "Unusually many font families",
            "severity": "low",
            "detail": f"The document embeds {len(signals.get('font_families') or [])} "
                      "distinct font families, which is unusual for a single "
                      "certificate. Advisory signal only.",
        })
    overlap = signals.get("text_image_overlap") or {}
    if overlap.get("overlay_ratio", 0.0) > 0.75 and overlap.get("total_text_blocks", 0) >= 3:
        anomalies.append({
            "key": "text_over_image_overlay",
            "label": "Text overlaid on raster image",
            "severity": "medium",
            "detail": "More than 75% of the text blocks overlap raster images, "
                      "consistent with text pasted over an image. Advisory signal only.",
        })