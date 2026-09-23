import type { EvidenceDetails } from "../types";
import type { ResultView } from "./result";

export type Severity = "low" | "medium" | "high" | "critical";

export interface ForensicFinding {
  id: string;
  group: string;
  label: string;
  detail: string;
  severity: Severity;
}

function normalizeSeverity(value: unknown): Severity {
  const s = String(value ?? "").toLowerCase();
  if (s === "critical") return "critical";
  if (s === "high") return "high";
  if (s === "medium" || s === "warn" || s === "warning") return "medium";
  return "low";
}

/** A neutral info finding derived from structural facts (not a warning). */
function infoFinding(id: string, group: string, label: string, detail: string): ForensicFinding {
  return { id, group, label, detail, severity: "low" };
}

/**
 * Build the forensic findings list strictly from backend-provided data.
 * Nothing here is invented; missing data simply produces no finding.
 */
export function buildForensicFindings(result: ResultView): ForensicFinding[] {
  const findings: ForensicFinding[] = [];
  const det = result.evidenceDetails ?? {};
  const intelligence = result.intelligence ?? {};
  const quality = intelligence.quality_indicators ?? {};

  // PDF forensics anomalies
  for (const anomaly of det.forensic_anomalies ?? []) {
    findings.push({
      id: `forensic-${anomaly.key ?? anomaly.label}`,
      group: "Document forensics",
      label: anomaly.label ?? anomaly.key ?? "Forensic anomaly",
      detail: anomaly.detail ?? "Detected in the PDF structure.",
      severity: normalizeSeverity(anomaly.severity),
    });
  }

  // Tampering findings
  const tampering: NonNullable<EvidenceDetails["tampering"]> =
    det.tampering ?? { status: "", findings: [] };
  const tamperingFindings = Array.isArray(tampering.findings)
    ? (tampering.findings as Array<Record<string, unknown>>)
    : [];
  for (const t of tamperingFindings) {
    findings.push({
      id: `tamper-${t.key ?? t.label ?? t.detail ?? Math.random()}`,
      group: "Tampering analysis",
      label: (t.label as string) ?? "Tampering indicator",
      detail: (t.detail as string) ?? String(t.key ?? "Detected in rendered image."),
      severity: normalizeSeverity(t.severity),
    });
  }
  if (tampering.status && String(tampering.status) !== "clean" && tamperingFindings.length === 0) {
    findings.push({
      id: "tamper-status",
      group: "Tampering analysis",
      label: "Tampering check status",
      detail: `Tampering analysis returned "${tampering.status}".`,
      severity: String(tampering.status).includes("suspect") ? "high" : "medium",
    });
  }

  // Risk signals
  for (const s of result.riskSignals ?? []) {
    findings.push({
      id: `risk-${s.key}`,
      group: "Risk signals",
      label: s.label,
      detail: s.detail,
      severity: normalizeSeverity(s.severity),
    });
  }

  // Consistency findings
  for (const f of intelligence.consistency_findings ?? []) {
    findings.push({
      id: `consistency-${f.key ?? f.label}`,
      group: "Identity consistency",
      label: f.label ?? "Consistency finding",
      detail: f.detail ?? "",
      severity: normalizeSeverity(f.severity),
    });
  }

  // Visual signals
  const visual = det.visual ?? {};
  const visualSignals = visual.signals ?? visual;
  if (visualSignals && typeof visualSignals === "object") {
    const record = visualSignals as Record<string, unknown>;
    for (const [key, value] of Object.entries(record)) {
      if (value === true || value === "yes") {
        findings.push({
          id: `visual-${key}`,
          group: "Visual analysis",
          label: readableKey(key),
          detail: "Detected in the rendered document image.",
          severity: "medium",
        });
      }
    }
  }

  // QR findings
  const qr: NonNullable<EvidenceDetails["qr"]> =
    det.qr ?? { status: "", count: 0, codes: [] };
  if (qr.status) {
    if (qr.invalid_qr) {
      findings.push({
        id: "qr-invalid",
        group: "QR analysis",
        label: "Invalid QR code",
        detail: "A QR code was present but could not be decoded reliably.",
        severity: "medium",
      });
    }
    if ((qr.count ?? 0) > 0 && !qr.invalid_qr) {
      findings.push(infoFinding(
        "qr-present",
        "QR analysis",
        "QR code present",
        `${qr.count} QR code${(qr.count ?? 0) > 1 ? "s" : ""} decoded on the document.`,
      ));
    }
  }

  // Issuer findings
  const issuer: NonNullable<EvidenceDetails["issuer"]> = det.issuer ?? { status: "" };
  if (issuer.status) {
    const statusStr = String(issuer.status);
    if (statusStr.includes("block") || statusStr.includes("blocklist")) {
      findings.push({
        id: "issuer-blocklist",
        group: "Issuer verification",
        label: "Issuer on blocklist",
        detail: issuer.notes?.join(" ") ?? "The extracted issuer matches a known-blocklist entry.",
        severity: "high",
      });
    } else if (statusStr.includes("unknown") || statusStr === "no_qr") {
      findings.push(infoFinding(
        "issuer-unknown",
        "Issuer verification",
        "Issuer not in registry",
        "The extracted issuer is not present in the known-issuer registry. This is not treated as fraud.",
      ));
    } else if (statusStr.includes("mismatch")) {
      findings.push({
        id: "issuer-mismatch",
        group: "Issuer verification",
        label: "Issuer domain mismatch",
        detail: "The QR/verification domain conflicts with the declared issuer.",
        severity: "medium",
      });
    } else if (statusStr.includes("verified") || statusStr.includes("known")) {
      findings.push(infoFinding(
        "issuer-known",
        "Issuer verification",
        "Issuer recognized",
        `The issuer "${issuer.issuer_name ?? "—"}" is present in the known-issuer registry.`,
      ));
    }
  }

  // Document quality
  if (quality.blank_document) {
    findings.push({
      id: "blank-doc",
      group: "Document quality",
      label: "Blank or near-empty document",
      detail: "The document contains little or no visible content.",
      severity: "medium",
    });
  }
  if (result.extraction?.ocr_failed) {
    findings.push({
      id: "ocr-failed",
      group: "Document extraction",
      label: "OCR failed",
      detail: "Text could not be recovered from this document. This is treated as an extraction limitation, not fraud.",
      severity: "medium",
    });
  }

  return findings;
}

function readableKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}