# Universal Certificate Forensics (Phase 12)

The evidence engine treats every certificate as a document to be forensically
examined. PDF forensics is the lowest layer of the Phase 12 evidence pipeline:
it inspects the physical PDF structure independent of the ML model, text
extraction, or any issuer-specific knowledge.

## Module

`app/services/pdf_forensics.py` — `analyze_pdf(pdf_bytes, filename)`.

## Signals produced

Each signal is emitted only when the underlying PDF facts are certain; unknown
or unreadable state never fabricates evidence.

| Signal | Meaning | Evidence status |
| --- | --- | --- |
| `launch_action` | PDF contains an embedded launch/open action | FAIL (warn-level) |
| `javascript` | PDF embeds a JavaScript action (rare in certificates, common in malware) | FAIL (warn-level) |
| `embedded_files` | PDF embeds attachments / file streams | FAIL (warn-level) |
| `malformed` | PDF structure is corrupt or unparseable by PyMuPDF | FAIL (error-level) |
| `encrypted` | PDF requires a password / is encrypted | FAIL (error-level) |
| `metadata_fields` | Producer/creator metadata present (baseline fact, not evidence of fraud) | PASS |
| `metadata_producer_mismatch` | Producer string conflicts with the declared issuer | FAIL (warn-level) |
| `file_sha256` | SHA-256 of the uploaded bytes (for duplicate + tamper linkage) | info |

## Guardrails

- **Absence is never evidence of fraud.** A PDF with no JavaScript, no
  embedded files and no launch action simply reports `clean`; it does not
  contribute a FAIL.
- **Malformed ≠ fake.** A corrupt or encrypted PDF is reported as an
  `error`-level FAIL that drives the final assessment toward
  `INSUFFICIENT_EVIDENCE`, never toward `LIKELY_SUSPICIOUS` by itself.
- All forensics run inside a `try/except` in the Phase 12 pipeline so a
  parsing failure can never break the core verification flow.

## Relationship to other layers

Forensics failures feed the fusion layer as one independent category. A
JavaScript/embedded-file PDF also gets `launch_action`-class signals into the
visual layer (rendered page anomalies) and the anomaly layer, so the system can
combine multiple independent suspicious signals before raising the final
assessment.