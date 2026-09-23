import { useEffect, useState } from "react";
import { Link } from "../router/Router";
import { getHealth, getMetrics, getModelInfo } from "../services/api";
import { ApiError } from "../services/api";
import type { HealthResponse, MetricsResponse, ModelInfoResponse } from "../types";
import { formatDateShort, formatPercent } from "../utils/format";
import { reviewStatusToCaseStatus } from "../utils/status";
import { ErrorState, LoadingState } from "../components/ui/Feedback";
import { StatCard } from "../components/ui/DataDisplay";
import { StatusBadge } from "../components/ui/DataDisplay";
import { PageHeader } from "../components/layout/AppShell";

export function DashboardPage() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfoResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([getMetrics(), getModelInfo(), getHealth()])
      .then(([m, mi, h]) => {
        setMetrics(m);
        setModelInfo(mi);
        setHealth(h);
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "Could not load dashboard data.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reviewDist = metrics?.review_status_distribution ?? {};
  const totalReview = Object.values(reviewDist).reduce((a, b) => a + b, 0);
  const predictionDist = metrics?.prediction_distribution ?? {};

  return (
    <div>
      <PageHeader
        title="Certificate Verification Center"
        subtitle="Analyze certificate documents using machine learning classification, evidence fusion, issuer verification and forensic document checks. Every decision is derived from independent evidence sources."
        actions={
          <>
            <Link to="/verify" className="btn btn--primary btn--lg">
              Verify Certificate
            </Link>
            <Link to="/investigations" className="btn btn--ghost btn--lg">
              View Investigations
            </Link>
          </>
        }
      />

      {loading ? (
        <LoadingState label="Loading dashboard…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : metrics ? (
        <>
          <div className="dash-grid">
            <StatCard
              label="Total Verifications"
              value={metrics.total_verifications}
              tone="accent"
              hint="Documents analyzed by the platform"
            />
            <StatCard
              label="Verified"
              value={metrics.genuine_count}
              tone="verified"
              hint="AI prediction: likely genuine"
            />
            <StatCard
              label="Requires Verification"
              value={reviewDist["manual_review"] ?? 0}
              tone="requires_verification"
              hint="Flagged for manual review"
            />
            <StatCard
              label="Suspicious"
              value={metrics.suspicious_count}
              tone="suspicious"
              hint="AI prediction: suspicious"
            />
            <StatCard
              label="Insufficient Evidence"
              value="—"
              tone="neutral"
              hint="Not reported by the verification API"
            />
          </div>

          <div className="grid grid--aside section" style={{ marginTop: 20 }}>
            <div className="card">
              <div className="card__head">
                <h2>Recent verification cases</h2>
                <Link to="/investigations" className="link-row">
                  View all
                </Link>
              </div>
              {metrics.recent.length === 0 ? (
                <p className="muted" style={{ fontSize: 13 }}>
                  No verifications recorded yet. Upload a certificate to begin an
                  investigation.
                </p>
              ) : (
                <div className="group-list">
                  {metrics.recent.map((r) => {
                    const status = reviewStatusToCaseStatus(r.review_status);
                    return (
                      <Link
                        key={r.verification_id}
                        to={`/investigations/${r.verification_id}`}
                        className="group-list__item case-row"
                        onClick={undefined}
                      >
                        <span>
                          <span className="case-row__name">{r.filename ?? "Unnamed document"}</span>
                          <span className="case-row__sub">
                            {r.verification_id} · {formatDateShort(r.created_at)}
                          </span>
                        </span>
                        <span className="case-row__right">
                          <span className="badge badge--neutral">
                            {formatPercent(r.risk_score)} risk
                          </span>
                          {status ? <StatusBadge status={status} /> : null}
                        </span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="grid" style={{ gap: 16 }}>
              <div className="card">
                <div className="card__head">
                  <h2>System status</h2>
                </div>
                <div className="kv">
                  <div className="kv__item">
                    <span className="kv__label">Backend</span>
                    <span className="kv__value">
                      {health?.status === "ok" ? (
                        <span style={{ color: "var(--green)" }}>Operational</span>
                      ) : (
                        "Unavailable"
                      )}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__label">Model</span>
                    <span className="kv__value mono">{health?.model_version ?? "—"}</span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__label">Model loaded</span>
                    <span className="kv__value">
                      {health?.model_loaded ? "Yes" : "No"}
                    </span>
                  </div>
                  <div className="kv__item">
                    <span className="kv__label">Feature vector</span>
                    <span className="kv__value">{modelInfo?.features.length ?? "—"} features</span>
                  </div>
                </div>
              </div>

              {totalReview > 0 ? (
                <div className="card">
                  <div className="card__head">
                    <h2>Review status distribution</h2>
                  </div>
                  <div className="bar-list">
                    {Object.entries(reviewDist)
                      .sort((a, b) => b[1] - a[1])
                      .map(([key, count]) => (
                        <div className="bar-row" key={key}>
                          <span className="bar-row__label">
                            {key === "low_risk"
                              ? "Low risk"
                              : key === "manual_review"
                                ? "Manual review"
                                : "High risk"}
                          </span>
                          <span className="bar-row__track">
                            <span
                              className="bar-row__fill"
                              style={{ width: `${Math.round((count / totalReview) * 100)}%` }}
                            />
                          </span>
                          <span className="bar-row__value">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>
              ) : null}

              {Object.keys(predictionDist).length > 0 ? (
                <div className="card">
                  <div className="card__head">
                    <h2>ML prediction distribution</h2>
                  </div>
                  <div className="bar-list">
                    {Object.entries(predictionDist).map(([key, count]) => (
                      <div className="bar-row" key={key}>
                        <span className="bar-row__label">{key}</span>
                        <span className="bar-row__track">
                          <span
                            className={`bar-row__fill ${
                              key === "suspicious" ? "bar-row__fill--suspicious" : ""
                            }`}
                            style={{
                              width: `${Math.round(
                                (count / metrics.total_verifications) * 100,
                              )}%`,
                            }}
                          />
                        </span>
                        <span className="bar-row__value">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}