import type { EvidenceDetails } from "../../types";
import type { ResultView } from "../../utils/result";
import { KeyValue, KeyValueGrid, SeverityBadge } from "../ui/DataDisplay";
import { EmptyState } from "../ui/Feedback";

export function TamperingPanel({ result }: { result: ResultView }) {
  const tampering: NonNullable<EvidenceDetails["tampering"]> =
    result.evidenceDetails?.tampering ?? { status: "", findings: [] };
  const visual = result.evidenceDetails?.visual ?? {};
  const visualSignals = (visual.signals ?? visual) as Record<string, unknown> | undefined;

  const findings = Array.isArray(tampering.findings) ? tampering.findings : [];
  const statusStr = tampering.status ? String(tampering.status) : "";
  const statusLabel =
    statusStr.includes("suspect") || statusStr.includes("tampered")
      ? "Tampering indicators detected"
      : statusStr === "clean"
        ? "No tampering indicators"
        : statusStr || "Not available";

  const signalEntries = visualSignals
    ? Object.entries(visualSignals).filter(
        ([, v]) => v === true || v === "yes" || v === 1,
      )
    : [];

  return (
    <div>
      <div className="card">
        <div className="card__head">
          <h2>Tampering analysis</h2>
          <span
            className={`evidence-status ${
              statusStr.includes("suspect") || statusStr.includes("tampered")
                ? "evidence-status--fail"
                : statusStr === "clean"
                  ? "evidence-status--pass"
                  : "evidence-status--unknown"
            }`}
          >
            {statusStr.includes("suspect") || statusStr.includes("tampered")
              ? "Fail"
              : statusStr === "clean"
                ? "Pass"
                : "Unknown"}
          </span>
        </div>
        <KeyValueGrid>
          <KeyValue label="Status" value={statusLabel} />
          <KeyValue
            label="Detected findings"
            value={findings.length}
            muted={findings.length === 0}
          />
          <KeyValue
            label="Visual anomalies"
            value={signalEntries.length}
            muted={signalEntries.length === 0}
          />
        </KeyValueGrid>

        {findings.length > 0 ? (
          <div className="finding-list" style={{ marginTop: 14 }}>
            {findings.map((f, idx) => {
              const rec = f as Record<string, unknown>;
              return (
                <div className="finding" key={String(rec.key ?? rec.label ?? idx)}>
                  <div className="finding__body">
                    <div className="finding__head">
                      <span className="finding__label">
                        {(rec.label as string) ?? (rec.key as string) ?? "Tampering finding"}
                      </span>
                      {rec.severity ? <SeverityBadge severity={String(rec.severity)} /> : null}
                    </div>
                    {rec.detail ? (
                      <p className="finding__detail">{String(rec.detail)}</p>
                    ) : null}
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

      <p className="muted" style={{ fontSize: 12, marginTop: 14 }}>
        Tampering detection is heuristic and best-effort. The absence of
        findings does not prove a document is authentic, and a failure to
        analyze is never treated as proof of tampering.
      </p>
    </div>
  );
}