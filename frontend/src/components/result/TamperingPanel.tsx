import type { EvidenceDetails } from "../../types";
import type { ResultView } from "../../utils/result";
import { EvidenceStatusChip, KeyValue, KeyValueGrid, SeverityBadge } from "../ui/DataDisplay";
import { EmptyState } from "../ui/Feedback";

const STATUS_META: Record<
  string,
  { label: string; chip: "PASS" | "WARNING" | "FAIL" | "UNKNOWN" }
> = {
  none_detected: { label: "No tampering indicators", chip: "PASS" },
  clean: { label: "No tampering indicators", chip: "PASS" },
  possible: { label: "Possible tampering indicators", chip: "WARNING" },
  suspect: { label: "Possible tampering indicators", chip: "WARNING" },
  strong_indicators: { label: "Strong tampering indicators", chip: "FAIL" },
  tampered: { label: "Strong tampering indicators", chip: "FAIL" },
  unable_to_determine: { label: "Unable to determine tampering status", chip: "UNKNOWN" },
};

function textValue(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

export function TamperingPanel({ result }: { result: ResultView }) {
  const tampering: NonNullable<EvidenceDetails["tampering"]> =
    result.evidenceDetails?.tampering ?? { status: "", findings: [] };
  const statusValue = typeof tampering.status === "string" ? tampering.status : "";
  const statusMeta = STATUS_META[statusValue];
  const findings = Array.isArray(tampering.findings) ? tampering.findings : [];
  const visual = result.evidenceDetails?.visual ?? {};
  const visualKeys = Object.keys(visual);

  return (
    <div className="tampering-panel">
      <div className="card">
        <div className="card__head">
          <div>
            <h2>Tampering analysis</h2>
            <p className="card__head-sub">Rendered-document and structural checks</p>
          </div>
          <EvidenceStatusChip status={statusMeta?.chip ?? "UNKNOWN"} />
        </div>
        <KeyValueGrid>
          <KeyValue
            label="Status"
            value={statusMeta?.label ?? (statusValue || "Not available")}
            muted={!statusMeta && !statusValue}
          />
          <KeyValue
            label="Detected findings"
            value={findings.length}
            muted={findings.length === 0}
          />
          <KeyValue
            label="Visual analysis"
            value={visualKeys.length > 0 ? "Data returned" : "Not available"}
            muted={visualKeys.length === 0}
          />
        </KeyValueGrid>

        {findings.length > 0 ? (
          <div className="finding-list tampering-findings">
            {findings.map((finding, index) => {
              const record =
                finding && typeof finding === "object"
                  ? (finding as Record<string, unknown>)
                  : {};
              const kind = textValue(record.kind);
              const label = textValue(record.label) ?? kind ?? "Tampering finding";
              const detail = textValue(record.detail);
              const severity = textValue(record.severity);
              const key = kind ?? label ?? `finding-${index}`;
              return (
                <div className="finding" key={`${key}-${index}`}>
                  <div className="finding__body">
                    <div className="finding__head">
                      <span className="finding__label">{label}</span>
                      {severity ? <SeverityBadge severity={severity} /> : null}
                    </div>
                    {kind ? <span className="finding__group">{kind}</span> : null}
                    {detail ? <p className="finding__detail">{detail}</p> : null}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <EmptyState
            compact
            icon="shield"
            title="No tampering findings"
            message="No explicit tampering indicators were reported for this document."
          />
        )}
      </div>
      <p className="report-note">
        Tampering detection is heuristic and best-effort. The absence of
        findings does not prove a document is authentic, and a failure to
        analyze is never treated as proof of tampering.
      </p>
    </div>
  );
}
