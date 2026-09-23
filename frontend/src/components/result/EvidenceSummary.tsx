import type { EvidenceItem } from "../../types";
import { EVIDENCE_STATUS_LABELS, evidenceCategoryLabel } from "../../utils/status";
import type { ResultView } from "../../utils/result";
import { EvidenceStatusChip } from "../ui/DataDisplay";

const CATEGORY_ORDER = [
  "ML",
  "EXTRACTION",
  "STRUCTURE",
  "SEMANTICS",
  "CONSISTENCY",
  "FORENSICS",
  "VISUAL",
  "TAMPERING",
  "QR",
  "ISSUER",
  "ANOMALY",
  "DUPLICATE",
  "EXTERNAL",
];

export function EvidenceSummary({ result }: { result: ResultView }) {
  const evidence = result.evidence;
  if (!evidence) {
    return (
      <div className="card">
        <div className="card__head">
          <h2>Evidence summary</h2>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          No evidence-engine block was returned for this verification. The
          platform's evidence fusion analysis is not available for this case.
        </p>
      </div>
    );
  }

  const statuses = evidence.category_status ?? {};
  const orderedKeys = CATEGORY_ORDER.filter((k) => k in statuses);
  const remaining = Object.keys(statuses).filter((k) => !orderedKeys.includes(k));
  const keys = [...orderedKeys, ...remaining];

  const items = evidence.evidence_items ?? [];

  return (
    <div>
      <div className="evidence-grid">
        {keys.length === 0 ? (
          <p className="muted" style={{ gridColumn: "1 / -1", fontSize: 13 }}>
            No category statuses were returned.
          </p>
        ) : (
          keys.map((key) => {
            const status = statuses[key] ?? "UNKNOWN";
            return (
              <div
                className={`evidence-card evidence-card--${String(status).toLowerCase()}`}
                key={key}
              >
                <div className="evidence-card__head">
                  <span className="evidence-card__title">
                    {evidenceCategoryLabel(key)}
                  </span>
                  <EvidenceStatusChip status={status} />
                </div>
                <p className="evidence-card__desc">{categoryDescription(key, status)}</p>
              </div>
            );
          })
        )}
      </div>

      {items.length > 0 ? (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="card__head">
            <h2>Evidence findings</h2>
            <span className="card__head-sub">{items.length} recorded</span>
          </div>
          <ul className="evidence-timeline">
            {items.map((item: EvidenceItem, idx: number) => {
              const cls = String(item.status).toLowerCase();
              return (
                <li
                  key={`${item.category}-${item.signal}-${idx}`}
                  className="evidence-timeline__item"
                >
                  <span
                    className={`evidence-timeline__dot evidence-timeline__dot--${cls}`}
                    aria-hidden="true"
                  />
                  <div className="evidence-timeline__head">
                    <EvidenceStatusChip status={item.status} />
                    <span className="evidence-timeline__cat">
                      {evidenceCategoryLabel(item.category)}
                    </span>
                    <span className="evidence-timeline__signal">{item.signal}</span>
                  </div>
                  <p className="evidence-timeline__detail">{item.explanation}</p>
                  {typeof item.confidence === "number" ? (
                    <span className="evidence-timeline__conf">
                      {EVIDENCE_STATUS_LABELS[item.status] ?? item.status} · confidence{" "}
                      {Math.round(item.confidence * 100)}%
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function categoryDescription(category: string, status: string): string {
  const base =
    status === "PASS"
      ? "No issues found in this evidence source."
      : status === "WARNING"
        ? "One or more caution signals were noted."
        : status === "FAIL"
          ? "This evidence source raised a concern."
          : "This evidence source could not be evaluated.";
  const specifics: Record<string, string> = {
    ML: "ML classifier risk assessment.",
    EXTRACTION: "Document text extraction reliability.",
    STRUCTURE: "Certificate document structure.",
    SEMANTICS: "Content-level plausibility and OOD checks.",
    CONSISTENCY: "Identity and field consistency checks.",
    FORENSICS: "PDF structural forensics.",
    VISUAL: "Rendered document visual analysis.",
    TAMPERING: "Visual tampering detection.",
    QR: "QR code presence and verification-page checks.",
    ISSUER: "Issuer registry and domain verification.",
    ANOMALY: "Aggregate anomaly scoring.",
    DUPLICATE: "Reuse against prior verifications.",
    EXTERNAL: "External verification (disabled by default).",
  };
  return `${specifics[category] ?? "Evidence source."} ${base}`;
}