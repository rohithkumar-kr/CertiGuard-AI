# Issuer Verification (Phase 12)

`app/services/issuer/` adds issuer-level intelligence as one independent
evidence category. It is strictly an advisory layer — it never modifies ML
features or the model prediction.

## Components

- `issuer_registry.json` — a small, explicit registry of known issuers
  (name, aliases, domains).
- `issuer_registry.py` — loads the registry and provides lookup by exact name,
  alias, or a normalized domain; also exposes the blocklist.
- `adapters.py` — adapter functions used by the Phase 12 pipeline
  (`analyze_issuer(...)`), returning a structured verdict object.

## Signals

| Signal | Meaning | Evidence status |
| --- | --- | --- |
| `issuer_known` | Issuer matches the registry (exact name or alias) | PASS |
| `domain_consistency` | QR/verification domain matches the issuer's declared domain | PASS |
| `issuer_unknown` | Issuer not present in the registry | WARNING |
| `domain_mismatch` | Issuer is known but the QR domain conflicts | WARNING |
| `blocklisted` | Issuer matches the blocklist | FAIL (high severity) |

## Invariants (unit-tested in `tests/test_phase12_evidence.py`)

- **Unknown issuer ≠ fake.** `issuer_unknown` is a WARNING only.
- A known issuer with no QR present reports `domain_consistency = no_qr`
  (a neutral fact, not a FAIL).
- A blocked issuer is a high-severity FAIL that contributes to
  `LIKELY_SUSPICIOUS` when combined with other signals.
- Issuer findings never feed the 31 ML features; `issuer_known` and
  `issuer_domain_trust` remain sourced exactly as before Phase 12.

## Registry policy

The registry is explicit and versionable. New issuers are added deliberately
(as data, not code), and the blocklist is reserved for issuers with
documented fraudulent activity — never for issuers we merely do not know.