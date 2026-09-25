import type { VerificationRecord } from "../../types";
import { formatDateShort, formatPercent } from "../../utils/format";
import { reviewStatusToCaseStatus } from "../../utils/status";
import { StatusBadge } from "../ui/DataDisplay";
import { EmptyState, LoadingState } from "../ui/Feedback";
import { Link } from "../../router/Router";

function certTypeLabel(raw: string | null): string {
  if (!raw) return "—";
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      const present = Object.entries(parsed)
        .filter(([, v]) => v)
        .map(([k]) => k);
      return present.join(", ") || "—";
    }
  } catch {
    /* fall through to raw */
  }
  return raw;
}

export function InvestigationTable({
  records,
  loading,
  error,
}: {
  records: VerificationRecord[];
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <LoadingState compact label="Loading investigations…" />;
  }
  if (error) {
    return (
      <EmptyState
        compact
        icon="warning"
        title="Could not load investigations"
        message={error}
      />
    );
  }
  if (records.length === 0) {
    return (
      <EmptyState
        icon="document"
        title="No investigations found"
        message="No verification cases match the current filters. Upload a certificate to create the first case."
      />
    );
  }

  return (
    <div className="card card--flush">
      <div className="table-wrap">
        <table className="table invest-table">
          <thead>
            <tr>
              <th>Case ID</th>
              <th>Document</th>
              <th>Date</th>
              <th>Status</th>
              <th>Risk</th>
              <th>Type</th>
              <th>Issuer</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => {
              const status = reviewStatusToCaseStatus(r.review_status);
              return (
                <tr key={r.verification_id}>
                  <td>
                    <Link
                      to={`/investigations/${r.verification_id}`}
                      className="mono table__primary"
                    >
                      {r.verification_id}
                    </Link>
                  </td>
                  <td title={r.filename ?? undefined}>
                    <span className="table__primary">{r.filename ?? "—"}</span>
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>{formatDateShort(r.created_at)}</td>
                  <td>
                    {status ? (
                      <StatusBadge status={status} />
                    ) : (
                      <span className="badge badge--neutral">Unknown</span>
                    )}
                  </td>
                  <td>
                    <span
                      style={{
                        color:
                          r.risk_score >= 0.5
                            ? "var(--red)"
                            : r.risk_score >= 0.3
                              ? "var(--amber)"
                              : "var(--green)",
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {formatPercent(r.risk_score)}
                    </span>
                  </td>
                  <td style={{ fontSize: 12.5 }}>{certTypeLabel(r.certificate_type)}</td>
                  <td title={r.issuer ?? undefined} style={{ fontSize: 12.5, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.issuer ?? "—"}
                  </td>
                  <td>
                    <div className="invest-table__actions">
                      <Link to={`/investigations/${r.verification_id}`} className="btn btn--sm btn--accent">
                        View Investigation
                      </Link>
                      <Link to={`/investigations/${r.verification_id}/raw`} className="btn btn--sm btn--ghost">
                        View Report
                      </Link>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {error ? <span className="sr-only" role="alert">{error}</span> : null}
    </div>
  );
}