import type { EvidenceDetails } from "../types";
import type { ResultView } from "./result";

export type Severity = "low" | "medium" | "high" | "critical" | "unknown";

export interface ForensicFinding {
  id: string;
  group: string;
  label: string;
  detail: string;
  severity: Severity;
}

function normalizeSeverity(value: unknown): Severity {
  const severity = String(value ?? "").toLowerCase();
  if (severity === "critical") return "critical";
  if (severity === "high") return "high";
  if (severity === "medium" || severity === "warn" || severity === "warning") return "medium";
  return "unknown";
}

function textValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function buildForensicFindings(result: ResultView): ForensicFinding[] {
  const findings: ForensicFinding[] = [];
  const details = result.evidenceDetails ?? {};
  const intelligence = result.intelligence ?? {};
  const quality = intelligence.quality_indicators ?? {};

  for (const [index, anomaly] of (details.forensic_anomalies ?? []).entries()) {
    const key = textValue(anomaly.key) ?? `anomaly-${index}`;
    findings.push({
      id: `forensic-${key}`,
      group: "Document forensics",
      label: textValue(anomaly.label) ?? key,
      detail: textValue(anomaly.detail) ?? "No detail was returned for this forensic anomaly.",
      severity: normalizeSeverity(anomaly.severity),
    });
  }

  const tampering: NonNullable<EvidenceDetails["tampering"]> =
    details.tampering ?? { status: "", findings: [] };
  const tamperingFindings = Array.isArray(tampering.findings)
    ? tampering.findings
    : [];
  tamperingFindings.forEach((value, index) => {
    const finding = recordValue(value);
    const key = textValue(finding.kind) ?? textValue(finding.key) ?? `finding-${index}`;
    findings.push({
      id: `tamper-${key}`,
      group: "Tampering analysis",
      label: textValue(finding.label) ?? key,
      detail: textValue(finding.detail) ?? "No detail was returned for this tampering finding.",
      severity: normalizeSeverity(finding.severity),
    });
  });

  for (const [index, signal] of (result.riskSignals ?? []).entries()) {
    const key = textValue(signal.key) ?? `signal-${index}`;
    findings.push({
      id: `risk-${key}`,
      group: "Risk signals",
      label: textValue(signal.label) ?? key,
      detail: textValue(signal.detail) ?? "No detail was returned for this risk signal.",
      severity: normalizeSeverity(signal.severity),
    });
  }

  for (const [index, finding] of (intelligence.consistency_findings ?? []).entries()) {
    const key = textValue(finding.key) ?? textValue(finding.label) ?? `finding-${index}`;
    findings.push({
      id: `consistency-${key}`,
      group: "Identity consistency",
      label: textValue(finding.label) ?? key,
      detail: textValue(finding.detail) ?? "No detail was returned for this consistency finding.",
      severity: normalizeSeverity(finding.severity),
    });
  }

  const visual = recordValue(details.visual);
  const visualSignals = recordValue(visual.signals ?? visual);
  for (const [key, value] of Object.entries(visualSignals)) {
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

  const qr: NonNullable<EvidenceDetails["qr"]> =
    details.qr ?? { status: "", count: 0, codes: [] };
  if (qr.status && qr.invalid_qr) {
    findings.push({
      id: "qr-invalid",
      group: "QR analysis",
      label: "Invalid QR code",
      detail: "A QR code was present but could not be decoded reliably.",
      severity: "medium",
    });
  }
  if (qr.status && typeof qr.count === "number" && qr.count > 0 && !qr.invalid_qr) {
    findings.push({
      id: "qr-present",
      group: "QR analysis",
      label: "QR code present",
      detail: `${qr.count} QR code${qr.count > 1 ? "s" : ""} decoded on the document.`,
      severity: "low",
    });
  }

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
      detail: "Text could not be recovered from this document. This is an extraction limitation, not fraud.",
      severity: "medium",
    });
  }

  return findings;
}

function readableKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
