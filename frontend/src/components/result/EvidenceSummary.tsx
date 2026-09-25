import type { EvidenceItem } from "../../types";
import type { ResultView } from "../../utils/result";
import {
  EVIDENCE_STATUS_LABELS,
  evidenceCategoryDescription,
  evidenceCategoryLabel,
} from "../../utils/status";
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
  "VERIFICATION_CODE",
  "ISSUER",
  "ANOMALY",
  "DUPLICATE",
];

export function EvidenceSummary({ result }: { result: ResultView }) {
  const evidence = result.evidence;
  if (!evidence) {
    return (
      <div className="card evidence-summary-empty">
        <p className="muted">
          No evidence-engine block was returned for this verification. The
          platform&apos;s evidence fusion analysis is not available for this case.
        </p>
      </div>
    );
  }

  const statuses = evidence.category_status ?? {};
  const orderedKeys = CATEGORY_ORDER.filter((key) => key in statuses);
  const remaining = Object.keys(statuses).filter((key) => !orderedKeys.includes(key));
  const keys = [...orderedKeys, ...remaining];
  const items = evidence.evidence_items ?? [];

  if (keys.length === 0) {
    return (
      <div className="card evidence-summary-empty">
        <p className="muted">No category statuses were returned.</p>
      </div>
    );
  }

  return (
    <div className="evidence-grid">
      {keys.map((key) => {
        const status = typeof statuses[key] === "string" ? statuses[key] : "UNKNOWN";
        const statusClass = status.toLowerCase();
        const finding = items.find(
          (item: EvidenceItem) => item.category === key,
        );
        return (
          <article
            className={`evidence-card evidence-card--${statusClass}`}
            key={key}
          >
            <div className="evidence-card__head">
              <span className="evidence-card__title">
                {evidenceCategoryLabel(key)}
              </span>
              <EvidenceStatusChip status={status} />
            </div>
            <p className="evidence-card__desc">
              {evidenceCategoryDescription(key)}
            </p>
            {finding ? (
              <p className="evidence-card__finding">
                <span>Finding</span>
                {finding.explanation || "No description was returned."}
              </p>
            ) : (
              <p className="evidence-card__status-copy">
                {EVIDENCE_STATUS_LABELS[status] ?? status} status returned.
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}
