import { useEffect, useMemo, useState } from "react";
import { ApiError, getVerificationAudit } from "../../services/api";
import type { AuditEvent } from "../../types";
import { formatDate } from "../../utils/format";
import { EmptyState, ErrorState, LoadingState } from "../ui/Feedback";

type FilterId =
  | "all"
  | "ml"
  | "forensics"
  | "issuer"
  | "tampering"
  | "evidence"
  | "review";

const FILTERS: Array<{ id: FilterId; label: string }> = [
  { id: "all", label: "All" },
  { id: "ml", label: "ML" },
  { id: "forensics", label: "Forensics" },
  { id: "issuer", label: "Issuer" },
  { id: "tampering", label: "Tampering" },
  { id: "evidence", label: "Evidence" },
  { id: "review", label: "Review" },
];

function eventFilterKeys(event: AuditEvent): FilterId[] {
  switch (event.event_type) {
    case "ML_ANALYSIS":
    case "FEATURE_EXTRACTION":
      return ["ml"];
    case "FORENSICS_ANALYSIS":
    case "VISUAL_ANALYSIS":
      return ["forensics"];
    case "ISSUER_ANALYSIS":
    case "VERIFICATION_CODE_ANALYSIS":
      return ["issuer"];
    case "TAMPERING_ANALYSIS":
      return ["tampering"];
    case "REVIEW_ACTION":
      return ["review"];
    default:
      return ["evidence"];
  }
}

const SEVERITY_LABELS: Record<string, string> = {
  success: "Success",
  info: "Info",
  warning: "Warning",
  error: "Error",
  unknown: "Unknown",
};

const EVENT_LABELS: Record<string, string> = {
  DOCUMENT_RECEIVED: "Document received",
  TEXT_EXTRACTION: "Text extraction",
  FEATURE_EXTRACTION: "Feature extraction",
  ML_ANALYSIS: "ML analysis",
  INTELLIGENCE_ANALYSIS: "Intelligence analysis",
  CONSISTENCY_ANALYSIS: "Consistency analysis",
  FORENSICS_ANALYSIS: "Forensics",
  VISUAL_ANALYSIS: "Visual analysis",
  TAMPERING_ANALYSIS: "Tampering",
  ISSUER_ANALYSIS: "Issuer verification",
  VERIFICATION_CODE_ANALYSIS: "Verification codes",
  EVIDENCE_FUSION: "Evidence fusion",
  FINAL_DECISION: "Final decision",
  REVIEW_ACTION: "Review action",
  PIPELINE_FAILED: "Pipeline failure",
};

function maskCode(value: unknown): string {
  const s = typeof value === "string" ? value : String(value ?? "");
  if (s.length <= 4) return "*".repeat(s.length || 1);
  return `${s.slice(0, 4)}${"*".repeat(Math.min(4, s.length - 4))}${s.slice(-3)}`;
}

function maskSensitive(value: Record<string, unknown>): Record<string, unknown> {
  // Defensive backstop: the backend already masks identifiers/codes before
  // they are stored; this guarantees nothing raw is ever rendered either.
  const sensitive = new Set([
    "code",
    "identifier",
    "token",
    "verification_code",
    "verification_codes",
    "cert_id",
    "credential_id",
  ]);
  const out: Record<string, unknown> = {};
  for (const [key, val] of Object.entries(value)) {
    if (sensitive.has(key)) {
      out[key] = maskCode(val);
    } else if (Array.isArray(val)) {
      out[key] = val.map((v) =>
        v && typeof v === "object" ? maskSensitive(v as Record<string, unknown>) : v,
      );
    } else if (val && typeof val === "object") {
      out[key] = maskSensitive(val as Record<string, unknown>);
    } else {
      out[key] = val;
    }
  }
  return out;
}

export function AuditTrailPanel({ verificationId }: { verificationId: string }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterId>("all");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getVerificationAudit(verificationId)
      .then((data) => {
        if (!cancelled) setEvents(data.events);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "Failed to load the audit trail.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [verificationId]);

  const retry = () => {
    setLoading(true);
    setError(null);
    getVerificationAudit(verificationId)
      .then((data) => setEvents(data.events))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Failed to load the audit trail."),
      )
      .finally(() => setLoading(false));
  };

  const filtered = useMemo(() => {
    if (filter === "all") return events;
    return events.filter((e) => eventFilterKeys(e).includes(filter));
  }, [events, filter]);

  const finalDecision = useMemo(
    () => events.find((e) => e.event_type === "FINAL_DECISION") ?? null,
    [events],
  );

  const toggle = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="card">
        <LoadingState label="Loading audit trail…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <ErrorState title="Audit trail unavailable" message={error} onRetry={retry} />
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="card">
        <EmptyState
          icon="document"
          title="No audit trail"
          message="No audit events were recorded for this verification."
        />
      </div>
    );
  }

  const decisionSeverity = SEVERITY_LABELS[finalDecision?.severity ?? ""]
    ? (finalDecision?.severity as string)
    : "unknown";

  return (
    <div className="card">
      <div className="card__head">
        <h2>Audit trail</h2>
        <span className="card__head-sub">
          Chronological record of what the system did — {events.length} event
          {events.length === 1 ? "" : "s"}
        </span>
      </div>

      {finalDecision ? (
        <div className={`audit-decision audit-decision--${decisionSeverity}`}>
          <span className="audit-decision__label">Final decision</span>
          <strong>{String(finalDecision.details.decision ?? "—")}</strong>
          {finalDecision.details.decision_summary ? (
            <span className="audit-decision__summary">
              {String(finalDecision.details.decision_summary)}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="audit-filters" role="group" aria-label="Filter audit trail">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`audit-filters__pill${filter === f.id ? " audit-filters__pill--active" : ""}`}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="muted" style={{ fontSize: 13, padding: "12px 0" }}>
          No events match this filter.
        </p>
      ) : null}

      <ol className="audit-timeline">
        {filtered.map((event) => {
          const severity = SEVERITY_LABELS[event.severity] ? event.severity : "unknown";
          const isOpen = expanded.has(event.id);
          const hasDetails = Object.keys(event.details ?? {}).length > 0;
          return (
            <li key={event.id} className={`audit-timeline__item audit-timeline__item--${severity}`}>
              <span className={`audit-timeline__dot audit-timeline__dot--${severity}`} aria-hidden="true" />
              <div className="audit-timeline__body">
                <div className="audit-timeline__head">
                  <span className="audit-timeline__title">{event.title}</span>
                  <span className="audit-timeline__time">{formatDate(event.created_at)}</span>
                </div>
                <div className="audit-timeline__meta">
                  <span className={`audit-chip audit-chip--${severity}`}>
                    {SEVERITY_LABELS[severity] ?? severity}
                  </span>
                  <span className="audit-timeline__type">
                    {EVENT_LABELS[event.event_type] ?? event.event_type}
                  </span>
                  {event.status ? <span className="audit-timeline__status">{event.status}</span> : null}
                </div>
                {event.description ? (
                  <p className="audit-timeline__detail">{event.description}</p>
                ) : null}
                {hasDetails ? (
                  <div className="audit-timeline__expand">
                    <button
                      type="button"
                      className="audit-timeline__toggle"
                      aria-expanded={isOpen}
                      onClick={() => toggle(event.id)}
                    >
                      {isOpen ? "Hide details" : "Show details"}
                    </button>
                    {isOpen ? (
                      <pre className="audit-timeline__json">
                        {JSON.stringify(maskSensitive(event.details), null, 2)}
                      </pre>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}