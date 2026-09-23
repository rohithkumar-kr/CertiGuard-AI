import { useState } from "react";
import type { EvidenceItem } from "../../types";
import { ASSESSMENT_LABELS } from "../../utils/status";
import { evidenceCategoryLabel } from "../../utils/status";
import type { ResultView } from "../../utils/result";
import { EvidenceStatusChip } from "../ui/DataDisplay";

const BRANCH_ORDER = [
  { key: "ML", desc: "Random-forest classifier risk assessment" },
  { key: "EXTRACTION", desc: "Text / OCR extraction reliability" },
  { key: "STRUCTURE", desc: "Certificate document structure" },
  { key: "SEMANTICS", desc: "Content plausibility & OOD checks" },
  { key: "CONSISTENCY", desc: "Identity and field consistency" },
  { key: "FORENSICS", desc: "PDF structural forensics" },
  { key: "VISUAL", desc: "Rendered image analysis" },
  { key: "TAMPERING", desc: "Visual tampering detection" },
  { key: "QR", desc: "QR / verification-code checks" },
  { key: "ISSUER", desc: "Issuer registry & domain verification" },
  { key: "ANOMALY", desc: "Aggregate anomaly scoring" },
  { key: "DUPLICATE", desc: "Reuse against prior verifications" },
  { key: "EXTERNAL", desc: "External verification (disabled by default)" },
];

export function FusionDiagram({ result }: { result: ResultView }) {
  const evidence = result.evidence;
  const [selected, setSelected] = useState<string | null>(null);

  if (!evidence) {
    return (
      <div className="card">
        <div className="card__head">
          <h2>Evidence fusion</h2>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          No evidence-fusion data was returned for this verification.
        </p>
      </div>
    );
  }

  const statuses = evidence.category_status ?? {};
  const branches = BRANCH_ORDER.filter((b) => b.key in statuses);
  const remaining = Object.keys(statuses).filter((k) => !BRANCH_ORDER.some((b) => b.key === k));
  const allBranches = [
    ...branches,
    ...remaining.map((k) => ({ key: k, desc: "Evidence source" })),
  ];

  const items = evidence.evidence_items ?? [];
  const selectedItems = selected
    ? items.filter((it: EvidenceItem) => it.category === selected)
    : [];
  const assessmentLabel =
    ASSESSMENT_LABELS[evidence.assessment] ?? evidence.assessment;

  return (
    <div className="card">
      <div className="card__head">
        <h2>Evidence fusion</h2>
        <span className="card__head-sub">No single signal decides the outcome</span>
      </div>

      <div className="fusion">
        <div className="fusion__node fusion__node--decision">
          Final decision · {assessmentLabel}
        </div>
        <div className="fusion__connector" aria-hidden="true" />
        <div className="fusion__node fusion__node--hub">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
            <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
          </svg>
          Evidence fusion
        </div>

        <div className="fusion__branches">
          {allBranches.map((branch) => {
            const status = statuses[branch.key] ?? "UNKNOWN";
            const isSelected = selected === branch.key;
            return (
              <button
                type="button"
                key={branch.key}
                className={`fusion__branch fusion__branch--${String(status).toLowerCase()}${
                  isSelected ? " fusion__branch--selected" : ""
                }`}
                aria-pressed={isSelected}
                onClick={() => setSelected(isSelected ? null : branch.key)}
              >
                <div className="fusion__branch-top">
                  <span className="fusion__branch-name">
                    {evidenceCategoryLabel(branch.key)}
                  </span>
                  <EvidenceStatusChip status={status} />
                </div>
                <span className="fusion__branch-desc">{branch.desc}</span>
              </button>
            );
          })}
        </div>

        <p className="fusion__note">
          The final decision is produced by a deterministic fusion of every
          independent evidence source above. Tap a source to see the findings
          that informed it.
        </p>
      </div>

      {selected ? (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>
            Findings · {evidenceCategoryLabel(selected)}
          </h3>
          {selectedItems.length > 0 ? (
            <ul className="evidence-timeline">
              {selectedItems.map((item: EvidenceItem, idx: number) => (
                <li
                  key={`${item.signal}-${idx}`}
                  className="evidence-timeline__item"
                >
                  <span
                    className={`evidence-timeline__dot evidence-timeline__dot--${String(
                      item.status,
                    ).toLowerCase()}`}
                    aria-hidden="true"
                  />
                  <div className="evidence-timeline__head">
                    <EvidenceStatusChip status={item.status} />
                    <span className="evidence-timeline__signal">{item.signal}</span>
                  </div>
                  <p className="evidence-timeline__detail">{item.explanation}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>
              No individual findings recorded for this evidence source.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}