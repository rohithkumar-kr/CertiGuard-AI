# Visual Analysis & Tampering Detection (Phase 12)

Two independent visual layers examine the rendered certificate image. Both run
after PDF/OCR extraction and are isolated from the ML feature pipeline.

## Visual analysis — `app/services/visual_analysis.py`

`analyze_visual(pdf_bytes, filename, images)` renders pages and measures
generic image statistics that are cheap and deterministic:

- **Blank ratio** — fraction of near-white/near-empty pixels; a
  mostly-blank certificate is a structural anomaly.
- **Sharpness** — Laplacian variance; unusually soft images suggest scanning
  artifacts or low-quality reproduction.
- **Noise** — global noise estimate.
- **Color anomaly** — unusual color statistics (e.g. heavy dark borders or
  screenshots).

Visual findings are `WARNING`-level signals; they raise suspicion only in
combination with other independent categories.

## Tampering detection — `app/services/tampering_service.py`

Detects manipulation of the rendered certificate image:

- **JPEG artifact detection** — measures DCT-block-grid coherence. Natural
  images and clean renders show little grid coherence; re-saved/re-compressed
  tampered images show strong block artifacts.
- **ELA (Error Level Analysis)** — high-variance regions under controlled
  re-compression indicate pixel-level modifications.
- **Clone/patch detection** — cross-correlation for repeated regions that
  suggest copy-paste forgery.

### Guardrails

- **Strong tampering increases suspicion** (fusion rule #9): a tampering FAIL
  contributes a high-severity signal toward `LIKELY_SUSPICIOUS`.
- Tampering checks are best-effort. If the page cannot be rendered or the
  image cannot be processed (OpenCV unavailable, malformed input), the category
  degrades to `UNKNOWN` and the verification continues — a failure to analyze
  is never treated as proof of tampering.
- Depends on `opencv-python-headless` (see `backend/requirements.txt`).

## Interaction with forensics

The PDF-forensics layer (`docs/universal_certificate_forensics.md`) inspects
the file structure while these layers inspect the rendered pixels. Together
they give independent structural and visual evidence that feeds the fusion
decision tree (`docs/evidence_fusion.md`).