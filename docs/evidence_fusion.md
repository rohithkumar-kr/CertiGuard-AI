# Evidence Fusion (Phase 12)

`app/services/evidence_fusion.py` combines the independent evidence categories
into a single assessment. Fusion is a deterministic decision tree — no learned
weights, no opaque scoring — so every verdict can be traced to the evidence
that produced it.

## Verdicts

| Assessment | Meaning |
| --- | --- |
| `LIKELY_GENUINE` | Multiple independent PASS signals and no meaningful FAIL |
| `LIKELY_SUSPICIOUS` | Multiple independent suspicious signals, or a high-severity structural failure |
| `REQUIRES_VERIFICATION` | Contradictory evidence or a single suspicious signal that is not sufficient on its own |
| `INSUFFICIENT_EVIDENCE` | Not enough extractable evidence to make a call |

## Inputs

Each input is an independent `EvidenceCategory` with a `status`
(`PASS` / `WARNING` / `FAIL` / `UNKNOWN`) and a severity:

- `ml` — model risk score, banded (low / elevated / high).
- `extraction` — method, completeness, OCR failure, extraction confidence.
- `structure` — document structure against generic certificate schema.
- `semantic` — content-level plausibility, OOD detection.
- `forensics` — PDF structural analysis (`pdf_forensics.py`).
- `visual` — rendered-page visual analysis (`visual_analysis.py`).
- `tampering` — visual tampering / manipulation detection (`tampering_service.py`).
- `qr` — QR code presence, parsing, verification-page detection.
- `issuer` — issuer registry, domain consistency, blocklist signals.
- `anomaly` — aggregate anomaly engine (`anomaly_service.py`).
- `external` — external verification (disabled by default; see below).
- `duplicate` — file / certificate-id / identity reuse.

## Fusion rules (encoded invariants)

The following principles are hard-coded as decision-tree branches and are
covered by unit tests (`tests/test_phase12_evidence.py`):

1. **Unknown issuer ≠ fake.** An issuer that is simply not in the registry is
   a `WARNING`, never a FAIL by itself.
2. **Image-only ≠ fake.** A scanned/image-only certificate is not evidence of
   fraud.
3. **Missing fields ≠ fake.** Missing extraction fields are an extraction
   limitation, not a fraud signal.
4. **OCR failure ≠ fake.** An OCR failure downgrades to `INSUFFICIENT_EVIDENCE`,
   never to `LIKELY_SUSPICIOUS`.
5. **OOD ≠ fake.** Out-of-distribution content is flagged for review, not
   condemned.
6. **QR absence ≠ fake.** A certificate without a QR code is not suspicious on
   that basis alone.
7. **Metadata anomalies ≠ fake alone.** PDF metadata oddities only raise
   suspicion together with other signals.
8. **High ML risk = evidence, not proof.** A high-risk ML prediction on a
   structurally clean document yields `REQUIRES_VERIFICATION`, not
   `LIKELY_SUSPICIOUS`.
9. **Strong tampering increases suspicion.** Visual tampering evidence raises
   the assessment toward `LIKELY_SUSPICIOUS`.
10. **Strong external verification increases genuine confidence.** A verified
    external match can counterbalance ML suspicion down to
    `REQUIRES_VERIFICATION`.
11. **Multiple independent suspicious signals increase suspicion.** Combined
    FAILs across independent categories escalate to `LIKELY_SUSPICIOUS`.
12. **Contradictions → REQUIRES_VERIFICATION.** Conflicting evidence never
    resolves to a confident verdict.
13. **Low-quality evidence → INSUFFICIENT_EVIDENCE.**
14. **No single weak signal dominates.**
15. **Never reduce fraud sensitivity.** Duplicate reuse and strong fraud
    signals always keep the assessment at or above `REQUIRES_VERIFICATION`.

## Duplicate handling in fusion

- File-content duplicate of a previously genuine document → medium-severity
  FAIL → `REQUIRES_VERIFICATION` (could be a legitimate re-upload or a
  recycled file).
- Duplicate certificate ID with different content → high-severity FAIL →
  `LIKELY_SUSPICIOUS`.

## External verification

`EXTERNAL_VERIFY_ENABLED` (default `false`, `app/core/config.py`) gates all
external network checks. When enabled:

- External checks use a short timeout and a bounded response size.
- QR existence never proves authenticity.
- An unknown QR domain is not fraud.
- The system never claims legal authenticity; the disclaimer stays in the UI.

## Failure containment

The pipeline calls each category inside `try/except` in
`app/services/phase12_pipeline.py`. A crash in any category degrades that
category to `UNKNOWN` and continues — the core verification response is never
lost to an evidence-layer exception.