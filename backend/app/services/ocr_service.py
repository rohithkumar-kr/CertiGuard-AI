"""Centralized OCR engine (Phase 10).

Provides a single, configurable OCR layer used by the extraction service:

  - ``rapidocr``  RapidOCR (ONNX Runtime) — bundles its own detection +
                  recognition models, so no external Tesseract binary is
                  required. Preferred engine. Uses the maintained ``rapidocr``
                  package; the retired ``rapidocr_onnxruntime`` is no longer a
                  dependency.
  - ``pytesseract`` Tesseract via pytesseract — used only when a Tesseract
                  binary is available on the system.
  - ``auto``     Try rapidocr, then pytesseract.
  - ``none`` / ``ocr_enabled=false``  OCR disabled entirely.

All OCR calls are best-effort and FAIL GRACEFULLY: a missing engine, missing
binary, or read error returns an ``OcrResult`` with ``failed=True`` and empty
text — it never raises into the verification pipeline.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from PIL import Image

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("ocr_service")

_rapid_engine = None
_rapid_engine_lock = threading.Lock()

_pytesseract_available: bool | None = None


@dataclass
class OcrResult:
    text: str = ""
    confidence: float | None = None
    failed: bool = False
    engine: str = "none"
    lines: int = 0
    error: str | None = None


# --------------------------------------------------------------------------
# Engine availability
# --------------------------------------------------------------------------

def _engine_selection() -> str:
    if not settings.ocr_enabled:
        return "none"
    engine = settings.ocr_engine or "auto"
    if engine not in ("auto", "rapidocr", "pytesseract", "none"):
        logger.warning("Unknown OCR_ENGINE=%r; falling back to auto", engine)
        return "auto"
    return engine


def _rapidocr_available() -> bool:
    try:
        import rapidocr  # noqa: F401
        return True
    except ImportError:
        return False


def _tesseract_available() -> bool:
    global _pytesseract_available
    if _pytesseract_available is not None:
        return _pytesseract_available
    try:
        import pytesseract  # type: ignore
        _pytesseract_available = bool(pytesseract.get_tesseract_version())
    except Exception:  # noqa: BLE001 - tesseract binary may be missing
        _pytesseract_available = False
    return _pytesseract_available


def _get_rapid_engine():
    global _rapid_engine
    if _rapid_engine is None:
        with _rapid_engine_lock:
            if _rapid_engine is None:
                # The maintained ``rapidocr`` package bundles the detection,
                # classification and recognition ONNX models. ONNX Runtime is
                # installed explicitly (see requirements.txt) and is used as
                # the default CPU execution engine.
                from rapidocr import RapidOCR
                _rapid_engine = RapidOCR()
    return _rapid_engine


# --------------------------------------------------------------------------
# Engine runners
# --------------------------------------------------------------------------

def _ocr_rapid(image: Image.Image, languages: str) -> OcrResult:
    import numpy as np

    engine = _get_rapid_engine()
    arr = np.array(image.convert("RGB"))
    try:
        result = engine(arr)
    except Exception as exc:  # noqa: BLE001 - OCR must fail gracefully
        logger.warning("RapidOCR failed: %s", exc)
        return OcrResult(failed=True, engine="rapidocr", error=str(exc))

    # The maintained ``rapidocr`` package returns a ``RapidOCROutput`` data
    # class (or an empty one when nothing was detected). ``txts``/``scores``
    # are parallel tuples and may be ``None`` when no text was found.
    txts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if not txts:
        return OcrResult(failed=True, engine="rapidocr", error="no text")

    lines = []
    confidences = []
    for i, raw_text in enumerate(txts):
        text = str(raw_text).strip() if raw_text is not None else ""
        if not text:
            continue
        lines.append(text)
        if scores is not None and i < len(scores):
            try:
                confidences.append(float(scores[i]))
            except (TypeError, ValueError):
                continue

    if not lines:
        return OcrResult(failed=True, engine="rapidocr", error="no text")
    confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )
    return OcrResult(
        text="\n".join(lines),
        confidence=confidence,
        failed=False,
        engine="rapidocr",
        lines=len(lines),
    )


def _ocr_pytesseract(image: Image.Image, languages: str) -> OcrResult:
    import pytesseract  # type: ignore

    try:
        data = pytesseract.image_to_data(
            image.convert("RGB"), lang=languages, output_type=pytesseract.Output.DICT
        )
    except Exception as exc:  # noqa: BLE001 - OCR must fail gracefully
        logger.warning("pytesseract failed: %s", exc)
        return OcrResult(failed=True, engine="pytesseract", error=str(exc))

    lines: list[str] = []
    confidences: list[float] = []
    current = []
    n = len(data.get("text", []))
    for i in range(n):
        conf = data.get("conf", [])[i]
        word = str(data.get("text", [])[i] or "")
        # conf == -1 means no confidence / blank line break.
        if int(data.get("line_num", [])[i]) > 0 and i > 0:
            pass
        if conf != "-1":
            try:
                confidences.append(float(conf) / 100.0)
            except (TypeError, ValueError):
                pass
        if word.strip():
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
                current = []
    if current:
        lines.append(" ".join(current))

    if not lines:
        return OcrResult(failed=True, engine="pytesseract", error="no text")
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    return OcrResult(
        text="\n".join(lines),
        confidence=confidence,
        failed=False,
        engine="pytesseract",
        lines=len(lines),
    )


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def is_available() -> bool:
    """True if at least one OCR engine could be used right now."""
    if not settings.ocr_enabled:
        return False
    selection = _engine_selection()
    if selection == "none":
        return False
    if selection in ("auto", "rapidocr"):
        if _rapidocr_available():
            return True
    if selection in ("auto", "pytesseract"):
        if _tesseract_available():
            return True
    return False


def ocr_image(image: Image.Image, languages: str | None = None) -> OcrResult:
    """Run OCR on a single image. Never raises; returns an OcrResult."""
    if not settings.ocr_enabled:
        return OcrResult(failed=True, engine="none", error="OCR disabled")
    lang = (languages or settings.ocr_languages or "en").strip() or "en"
    selection = _engine_selection()
    if selection == "none":
        return OcrResult(failed=True, engine="none", error="OCR disabled")

    if selection in ("auto", "rapidocr") and _rapidocr_available():
        result = _ocr_rapid(image, lang)
        if not result.failed:
            return result
        if selection == "rapidocr":
            return result  # explicit engine; do not fall through

    if selection in ("auto", "pytesseract") and _tesseract_available():
        return _ocr_pytesseract(image, lang)

    reason = "no OCR engine available (rapidocr and tesseract both unavailable)"
    logger.warning("OCR unavailable for this document: %s", reason)
    return OcrResult(failed=True, engine="none", error=reason)
