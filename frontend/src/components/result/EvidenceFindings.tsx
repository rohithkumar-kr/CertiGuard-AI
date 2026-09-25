import type { EvidenceItem } from "../../types";
import type { ResultView } from "../../utils/result";
import { evidenceCategoryLabel, EVIDENCE_STATUS_LABELS } from "../../utils/status";
import { EvidenceStatusChip } from "../ui/DataDisplay";

export function EvidenceFindings({ result }: { result: ResultView }) {
  const items = result.evidence?.evidence_items ?? [];

  if (items.length === 0) {
    return (
      <div className="card evidence-findings-empty">
        <p className="muted">No individual evidence findings were returned.</p>
      </div>
    );
  }

  return (
    <div className="card evidence-findings">
      <div className="card__head">
        <div>
          <h2>Evidence findings</h2>
          <p className="card__head-sub">Recorded signals and their explanations</p>
        </div>
        <span className="card__head-sub">{items.length} recorded</span>
      </div>
      <ol className="evidence-timeline evidence-timeline--report">
        {items.map((item: EvidenceItem, index: number) => {
          const status = item.status ?? "UNKNOWN";
          const statusClass = String(status).toLowerCase();
          const signal = item.signal || "Finding";
          return (
            <li
              className="evidence-timeline__item"
              key={`${item.category}-${signal}-${index}`}
            >
              <span
                className={`evidence-timeline__dot evidence-timeline__dot--${statusClass}`}
                aria-hidden="true"
              />
              <div className="evidence-timeline__head">
                <EvidenceStatusChip status={status} />
                <span className="evidence-timeline__cat">
                  {evidenceCategoryLabel(item.category)}
                </span>
                <span className="evidence-timeline__signal">{signal}</span>
              </div>
              <p className="evidence-timeline__detail">
                {item.explanation || "No description was returned for this finding."}
              </p>
              {typeof item.confidence === "number" && Number.isFinite(item.confidence) ? (
                <span className="evidence-timeline__conf">
                  {EVIDENCE_STATUS_LABELS[status] ?? status} · confidence{" "}
                  {Math.round(item.confidence * 100)}%
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
