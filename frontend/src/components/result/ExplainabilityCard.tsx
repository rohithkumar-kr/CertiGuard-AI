import type { ResultView } from "../../utils/result";
import { formatPercent } from "../../utils/format";
import { SeverityBadge } from "../ui/DataDisplay";
import { OOD_LABELS, PRIORITY_LABELS } from "../../utils/status";

function Icon({ name }: { name: "ok" | "warn" | "info" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="15"
      height="15"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {name === "ok" ? (
        <path d="m5 12 4 4L19 6" />
      ) : name === "warn" ? (
        <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      ) : (
        <path d="M12 16v-4M12 8h.01M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z" />
      )}
    </svg>
  );
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function ExplainabilityCard({ result }: { result: ResultView }) {
  const positive = result.positiveSignals ?? [];
  const risk = result.riskSignals ?? [];
  const findings = result.intelligence?.consistency_findings ?? [];
  const quality = result.intelligence?.quality_indicators ?? {};
  const riskScore = finiteNumber(result.riskScore);
  const certificateType = textValue(result.intelligence?.certificate_type?.primary);
  const issuer = textValue(result.issuer);
  const documentQuality =
    textValue(quality.text_extraction_quality) ?? textValue(quality.visual_quality);
  const blankDocument =
    typeof quality.blank_document === "boolean" ? quality.blank_document : null;
  const evidenceSummary = result.evidence?.summary ?? {};
  const anomalyLevel = textValue(evidenceSummary.anomaly_level);
  const anomalyScore = finiteNumber(evidenceSummary.anomaly_score);

  return (
    <div className="card">
      <div className="card__head">
        <h2>Why did the system reach this decision?</h2>
        <span className="card__head-sub">Human-readable interpretation</span>
      </div>

      <div className="kv" style={{ marginBottom: 18 }}>
        {textValue(result.prediction) ? (
          <div className="kv__item">
            <span className="kv__label">ML prediction</span>
            <span className="kv__value">{result.prediction}</span>
          </div>
        ) : null}
        {riskScore !== null ? (
          <div className="kv__item">
            <span className="kv__label">AI risk score</span>
            <span className="kv__value">{formatPercent(riskScore)}</span>
          </div>
        ) : null}
        {certificateType ? (
          <div className="kv__item">
            <span className="kv__label">Certificate type</span>
            <span className="kv__value">{certificateType}</span>
          </div>
        ) : null}
        {issuer ? (
          <div className="kv__item">
            <span className="kv__label">Issuer</span>
            <span className="kv__value">{issuer}</span>
          </div>
        ) : null}
        {blankDocument !== null ? (
          <div className="kv__item">
            <span className="kv__label">Blank document</span>
            <span className="kv__value">
              {blankDocument ? "Blank / mostly empty" : "No blank-document signal"}
            </span>
          </div>
        ) : null}
        {documentQuality ? (
          <div className="kv__item">
            <span className="kv__label">Document quality</span>
            <span className="kv__value">{documentQuality}</span>
          </div>
        ) : null}
        {result.oodStatus ? (
          <div className="kv__item">
            <span className="kv__label">Out-of-distribution</span>
            <span className="kv__value">
              {OOD_LABELS[result.oodStatus] ?? result.oodStatus}
            </span>
          </div>
        ) : null}
        {result.reviewPriority ? (
          <div className="kv__item">
            <span className="kv__label">Review priority</span>
            <span className="kv__value">
              {PRIORITY_LABELS[result.reviewPriority] ?? result.reviewPriority}
            </span>
          </div>
        ) : null}
        {anomalyLevel || anomalyScore !== null ? (
          <div className="kv__item">
            <span className="kv__label">Anomaly</span>
            <span className="kv__value">
              {anomalyLevel}
              {anomalyLevel && anomalyScore !== null ? " · " : null}
              {anomalyScore !== null ? anomalyScore.toFixed(2) : null}
            </span>
          </div>
        ) : null}
      </div>

      {positive.length > 0 ? (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "16px 0 10px" }}>
            What supports this document
          </h3>
          <ul className="group-list">
            {positive.map((s) => (
              <li key={s.key} className="group-list__item">
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start", minWidth: 0 }}>
                  <span style={{ color: "var(--green)", marginTop: 2 }}>
                    <Icon name="ok" />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", overflowWrap: "anywhere" }}>
                      {s.label}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 2, overflowWrap: "anywhere" }}>
                      {s.detail}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {risk.length > 0 ? (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "16px 0 10px" }}>
            What raises concern
          </h3>
          <ul className="group-list">
            {risk.map((s) => (
              <li key={s.key} className="group-list__item">
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start", minWidth: 0 }}>
                  <span style={{ color: "var(--amber)", marginTop: 2 }}>
                    <Icon name="warn" />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        flexWrap: "wrap",
                         fontSize: 13,
                         fontWeight: 600,
                         color: "var(--text-primary)",
                         overflowWrap: "anywhere",

                      }}
                    >
                      {s.label}
                      {s.severity ? <SeverityBadge severity={s.severity} /> : null}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 2, overflowWrap: "anywhere" }}>
                      {s.detail}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {findings.length > 0 ? (
        <>
          <h3 style={{ fontSize: 13, fontWeight: 600, margin: "16px 0 10px" }}>
            Consistency findings
          </h3>
          <ul className="group-list">
            {findings.map((f) => (
              <li key={f.key} className="group-list__item">
                <div style={{ display: "flex", gap: 10, alignItems: "flex-start", minWidth: 0 }}>
                  <span style={{ color: "var(--amber)", marginTop: 2 }}>
                    <Icon name="warn" />
                  </span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", overflowWrap: "anywhere" }}>
                      {f.label}
                    </div>
                    <div className="muted" style={{ fontSize: 12.5, marginTop: 2, overflowWrap: "anywhere" }}>
                      {f.detail}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {positive.length === 0 && risk.length === 0 && findings.length === 0 ? (
        <p className="muted" style={{ fontSize: 13 }}>
          No explicit positive or risk signals were recorded for this
          verification.
        </p>
      ) : null}

      {result.evidence?.summary?.strong_tampering ? (
        <div className="alert alert--warn" style={{ marginTop: 14 }}>
          <Icon name="warn" />
          <span>Tampering indicators were detected. This significantly raises
            suspicion and requires manual review.</span>
        </div>
      ) : null}
      {result.evidence?.summary?.externally_verified ? (
        <div className="alert alert--success" style={{ marginTop: 14 }}>
          <Icon name="ok" />
          <span>External verification succeeded, increasing confidence in this
            document.</span>
        </div>
      ) : null}

      <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>
        These are detected indicators, not proof of fraud. The platform is an
        AI-based preliminary screening tool, not a legal authenticity authority.
      </p>
    </div>
  );
}