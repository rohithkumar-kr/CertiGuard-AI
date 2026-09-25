import type { ReactNode } from "react";
import { CASE_STATUS_LABELS, EVIDENCE_STATUS_LABELS } from "../../utils/status";
import type { CaseStatus } from "../../utils/status";
import { formatPercent } from "../../utils/format";

/* ---------- Status badge ---------- */

export function StatusBadge({
  status,
  label,
}: {
  status: CaseStatus | string;
  label?: string;
}) {
  const text =
    label ??
    (status in CASE_STATUS_LABELS
      ? CASE_STATUS_LABELS[status as CaseStatus]
      : status);
  const cls = status in CASE_STATUS_LABELS ? status : "neutral";
  return (
    <span className={`badge badge--${cls}`}>
      <span aria-hidden="true">●</span>
      {text}
    </span>
  );
}

/* ---------- Evidence status chip ---------- */

export function EvidenceStatusChip({ status }: { status: string }) {
  const cls = String(status).toLowerCase();
  return (
    <span className={`evidence-status evidence-status--${cls}`}>
      {EVIDENCE_STATUS_LABELS[status] ?? status}
    </span>
  );
}

/* ---------- Severity badge ---------- */

export function SeverityBadge({ severity }: { severity: string }) {
  const cls = String(severity).toLowerCase();
  return <span className={`severity severity--${cls}`}>{cls}</span>;
}

/* ---------- Stat card ---------- */

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "verified" | "requires_verification" | "suspicious" | "neutral" | "accent";
}) {
  return (
    <div className={`stat-card stat-card--${tone}`}>
      <span className={`stat-card__value stat-card__value--${tone}`}>{value}</span>
      <span className="stat-card__label">{label}</span>
      {hint ? <span className="stat-card__hint">{hint}</span> : null}
    </div>
  );
}

/* ---------- Confidence indicator ---------- */

export function ConfidenceIndicator({
  value,
  tone = "neutral",
}: {
  value: number | null | undefined;
  tone?: "verified" | "requires_verification" | "suspicious" | "neutral" | "accent";
}) {
  const normalized =
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const pct = normalized === null ? null : Math.max(0, Math.min(100, Math.round(normalized * 100)));
  return (
    <div className="confidence">
      <div className="confidence__head">
        <span>Confidence</span>
        <strong>{pct === null ? "—" : `${pct}%`}</strong>
      </div>
      <div className="confidence__track" role="img" aria-label={`Confidence ${pct ?? 0}%`}>
        <div
          className={`confidence__fill confidence__fill--${tone}`}
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
    </div>
  );
}

/* ---------- Risk meter ---------- */

export function RiskMeter({ value }: { value: number | null | undefined }) {
  const normalized =
    typeof value === "number" && Number.isFinite(value) ? value : null;
  const pct = normalized === null ? null : Math.max(0, Math.min(100, Math.round(normalized * 100)));
  return (
    <div className="risk-meter">
      <div className="risk-meter__head">
        <span>Risk score</span>
        <strong>{pct === null ? "—" : formatPercent(normalized)}</strong>
      </div>
      <div className="risk-meter__track" role="img" aria-label={`Risk score ${pct ?? 0}%`}>
        <div className="risk-meter__fill" style={{ width: `${pct ?? 0}%` }} />
      </div>
    </div>
  );
}

/* ---------- Key/value pair ---------- */

export function KeyValue({
  label,
  value,
  muted,
  mono,
}: {
  label: string;
  value: ReactNode;
  muted?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="kv__item">
      <span className="kv__label">{label}</span>
      <span
        className={`kv__value${muted ? " kv__value--muted" : ""}${mono ? " mono" : ""}`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

export function KeyValueGrid({
  children,
}: {
  children: ReactNode;
}) {
  return <div className="kv">{children}</div>;
}