"""QR-code intelligence (Phase 12, M3).

Detects and decodes QR codes from a rendered certificate page, extracts the
payload's URL / domain, and — only when explicitly enabled — performs a
bounded external check against the verification URL.

Security rules:
  * a QR code's *existence* is never treated as proof of authenticity;
  * an undecodable QR is evidence, not fraud;
  * a QR pointing at an unknown domain is NOT automatically fraud;
  * external network calls are made ONLY when ``EXTERNAL_VERIFY_ENABLED=true``,
    with a short timeout and a bounded response size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from PIL import Image

from ..core.config import settings

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

# A bare domain-ish payload without scheme is still treated as a domain.
_DOMAIN_RE = re.compile(
    r"^(?:https?://)?([a-z0-9][a-z0-9.-]+\.[a-z]{2,})(?:[/?#].*)?$", re.IGNORECASE
)


@dataclass
class QRCodeResult:
    payload: str
    is_url: bool = False
    scheme: str | None = None
    domain: str | None = None
    tld: str | None = None
    is_https: bool = False
    path: str | None = None
    verification_page: bool = False
    external: dict | None = None


@dataclass
class QRReport:
    detected: bool = False
    count: int = 0
    invalid_qr: bool = False
    codes: list[QRCodeResult] = field(default_factory=list)
    status: str = "no_qr"
    notes: list = field(default_factory=list)


def _is_verification_path(path: str | None) -> bool:
    if not path:
        return False
    p = path.lower()
    return any(k in p for k in ("verif", "check", "certif", "credential"))


def parse_payload(payload: str) -> QRCodeResult:
    """Parse a decoded QR payload into URL/domain components."""
    res = QRCodeResult(payload=payload)
    if "://" in payload:
        parsed = urlparse(payload)
        if parsed.scheme in ("http", "https"):
            res.is_url = True
            res.scheme = parsed.scheme
            res.is_https = parsed.scheme == "https"
            res.domain = parsed.netloc.lower() if parsed.netloc else None
            res.path = parsed.path
    else:
        m = _DOMAIN_RE.match(payload.strip())
        if m:
            res.is_url = True
            res.scheme = "http"
            res.domain = m.group(1).lower()
            path = payload.strip()[len(m.group(1)):]
            res.path = path if path.startswith(("/", "?", "#")) else None
    if res.domain:
        parts = res.domain.rsplit(".", 2)
        res.tld = parts[-1] if len(parts) >= 2 else None
    res.verification_page = _is_verification_path(res.path) or bool(
        res.domain and any(k in res.domain for k in ("verify", "verif", "credential"))
    )
    return res


def _external_check(res: QRCodeResult) -> dict | None:
    """Bounded network check of the QR payload's URL (only when enabled)."""
    if not settings.external_verify_enabled:
        return None
    if not res.is_url or not res.scheme:
        return None
    if res.scheme not in settings.external_verify_schemes:
        return {"reachable": False, "detail": "scheme not allowed"}
    import urllib.request

    url = res.payload if "://" in res.payload else f"http://{res.payload}"
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "certificate-verify/2"})
    try:
        with urllib.request.urlopen(
            req, timeout=settings.external_verify_timeout
        ) as resp:
            status = getattr(resp, "status", None)
            return {"reachable": status is not None and 200 <= status < 400,
                    "status": status}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "detail": f"{type(exc).__name__}: {exc}"}


def analyze_qr(image: Image.Image) -> QRReport:
    """Detect and decode QR codes in a rendered certificate page."""
    report = QRReport()
    if cv2 is None:
        report.notes.append("OpenCV unavailable; QR decoding skipped.")
        report.status = "no_qr"
        return report

    try:
        img = image.convert("RGB")
        arr = cv2.cvtColor(__import__("numpy").asarray(img), cv2.COLOR_RGB2GRAY)
        detector = cv2.QRCodeDetector()
        try:
            result = detector.detectAndDecodeMulti(arr)
        except (AttributeError, cv2.error):  # pragma: no cover - API differences
            result = None
        if result is None:
            decoded, points = None, None
            text, pts, _ = detector.detectAndDecode(arr)
            if text:
                decoded, points = (text,), (pts,)
        else:
            # detectAndDecodeMulti returns (retval, decodedInfo, straightCode,
            # points) in OpenCV >= 4.x; older builds return fewer elements.
            if len(result) >= 4:
                decoded, _, _, points = result
            elif len(result) == 2:
                decoded, points = result
            else:
                decoded, points = result[0], None

        codes: list[QRCodeResult] = []
        if decoded:
            for i, text in enumerate(decoded if not isinstance(decoded, str) else (decoded,)):
                if not text:
                    continue
                res = parse_payload(text)
                res.external = _external_check(res)
                codes.append(res)
            # A QR image that could not be decoded at all (no text anywhere).
            if not codes and points is not None and len(points) > 0:
                report.invalid_qr = True
                report.notes.append("QR pattern detected but could not be decoded.")

        report.codes = codes
        report.count = len(codes)
        report.detected = report.count > 0 or report.invalid_qr

        if codes:
            verified = [c for c in codes if (c.external or {}).get("reachable")]
            vp = [c for c in codes if c.verification_page]
            if verified:
                report.status = "verified_externally"
            elif vp:
                report.status = "verification_page_found"
            else:
                report.status = "verification_unavailable"
        elif report.invalid_qr:
            report.status = "invalid_qr"
        else:
            report.status = "no_qr"
    except Exception as exc:  # noqa: BLE001 - QR analysis must never raise
        report.notes.append(f"QR analysis error: {exc}")
        report.status = "no_qr"
    return report