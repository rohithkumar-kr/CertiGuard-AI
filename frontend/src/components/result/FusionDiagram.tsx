import { useState } from "react";
import type { EvidenceItem } from "../../types";
import { ASSESSMENT_LABELS, evidenceCategoryDescription, evidenceCategoryLabel } from "../../utils/status";
import type { ResultView } from "../../utils/result";
import { EvidenceStatusChip } from "../ui/DataDisplay";

const BRANCH_ORDER = [
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

export function FusionDiagram({ result }: { result: ResultView }) {
  const evidence = result.evidence;
  const [selected, setSelected] = useState<string | null>(null);

  if (!evidence) {
    return (
      <div className="card fusion-card">
        <p className="muted">No evidence-fusion data was returned for this verification.</p>
      </div>
    );
  }

  const statuses = evidence.category_status ?? {};
  const orderedKeys = BRANCH_ORDER.filter((key) => key in statuses);
  const remaining = Object.keys(statuses).filter(
    (key) => !BRANCH_ORDER.includes(key),
  );
  const branches = [...orderedKeys, ...remaining];
  const items = evidence.evidence_items ?? [];
  const selectedItems = selected
    ? items.filter((item: EvidenceItem) => item.category === selected)
    : [];
  const assessmentLabel =
    ASSESSMENT_LABELS[evidence.assessment] ?? evidence.assessment ?? "Decision unavailable";

  return (
    <div className="card fusion-card">
      <div className="fusion-layout">
        <div className="fusion-contributors">
          <div className="fusion-panel-head">
            <h3>Evidence contributors</h3>
            <p>Select a source to inspect the findings it contributed.</p>
          </div>
          <div className="fusion-contributor-grid">
            {branches.map((key) => {
              const status =
                typeof statuses[key] === "string" ? statuses[key] : "UNKNOWN";
              const isSelected = selected === key;
              return (
                <button
                  type="button"
                  className={`fusion-contributor fusion-contributor--${status.toLowerCase()}${
                    isSelected ? " fusion-contributor--selected" : ""
                  }`}
                  key={key}
                  aria-pressed={isSelected}
                  onClick={() => setSelected(isSelected ? null : key)}
                >
                  <div className="fusion-contributor__top">
                    <span className="fusion-contributor__name">
                      {evidenceCategoryLabel(key)}
                    </span>
                    <EvidenceStatusChip status={status} />
                  </div>
                  <span className="fusion-contributor__description">
                    {evidenceCategoryDescription(key)}
                  </span>
                </button>
              );
            })}
          </div>
          {selected ? (
            <div className="fusion-selected">
              <div className="fusion-selected__head">
                <h4>Findings · {evidenceCategoryLabel(selected)}</h4>
                <span>{selectedItems.length} recorded</span>
              </div>
              {selectedItems.length > 0 ? (
                <ol className="evidence-timeline evidence-timeline--compact">
                  {selectedItems.map((item: EvidenceItem, index: number) => (
                    <li className="evidence-timeline__item" key={`${item.signal}-${index}`}>
                      <span
                        className={`evidence-timeline__dot evidence-timeline__dot--${item.status.toLowerCase()}`}
                        aria-hidden="true"
                      />
                      <div className="evidence-timeline__head">
                        <EvidenceStatusChip status={item.status} />
                        <span className="evidence-timeline__signal">{item.signal}</span>
                      </div>
                      <p className="evidence-timeline__detail">{item.explanation}</p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">No individual findings were recorded for this source.</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="fusion-arrow" aria-hidden="true">
          ↓
        </div>

        <aside className="fusion-decision" aria-label="Final decision">
          <p className="fusion-decision__eyebrow">Final decision</p>
          <div className="fusion-decision__title">{assessmentLabel}</div>
          <p className="fusion-decision__copy">
            The decision is produced from the combined status of the evidence
            contributors shown here.
          </p>
          <div className="fusion-decision__rule" />
          <p className="fusion-decision__note">
            No individual contributor is treated as a standalone verdict.
          </p>
        </aside>
      </div>
      <p className="fusion__note">
        The visualization shows the evidence inputs and their returned statuses;
        it does not invent contribution weights or numerical fusion values.
      </p>
    </div>
  );
}
