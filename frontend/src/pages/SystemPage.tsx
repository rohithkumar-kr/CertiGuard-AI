import { useEffect, useState } from "react";
import { ApiError, getHealth, getModelInfo, getMetrics } from "../services/api";
import type { HealthResponse, MetricsResponse, ModelInfoResponse } from "../types";
import { formatDate } from "../utils/format";
import { PageHeader } from "../components/layout/AppShell";
import { KeyValue, KeyValueGrid, StatCard } from "../components/ui/DataDisplay";
import { EmptyState, LoadingState } from "../components/ui/Feedback";
import { JsonBlock, TechnicalDetails } from "../components/ui/TechnicalDetails";

export function SystemPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfoResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch((e) => setHealthError(e instanceof ApiError ? e.message : "Health check failed."));
    getModelInfo()
      .then(setModelInfo)
      .catch(() => {
        /* model info is supplementary */
      });
    getMetrics()
      .then(setMetrics)
      .catch((e) => setMetricsError(e instanceof ApiError ? e.message : "Metrics unavailable."));
  }, []);

  return (
    <div>
      <PageHeader
        title="System Status"
        subtitle="Live backend health, the machine-learning model behind the risk score, and evidence-engine configuration."
      />

      <div className="grid grid--2" style={{ gap: 18 }}>
        <div className="card">
          <div className="card__head">
            <h2>Backend health</h2>
            {health ? (
              <span
                className={`badge ${health.status === "ok" && health.model_loaded ? "badge--success" : "badge--danger"}`}
              >
                {health.status === "ok" && health.model_loaded ? "Online" : "Degraded"}
              </span>
            ) : null}
          </div>
          {health ? (
            <KeyValueGrid>
              <KeyValue label="API status" value={health.status} />
              <KeyValue label="Application" value={health.app} />
              <KeyValue label="Model loaded" value={health.model_loaded ? "Yes" : "No"} />
              <KeyValue label="Model version" value={health.model_version ?? "—"} mono />
            </KeyValueGrid>
          ) : healthError ? (
            <EmptyState compact icon="warning" title="Health check unavailable" message={healthError} />
          ) : (
            <LoadingState compact label="Checking backend…" />
          )}
        </div>

        <div className="card">
          <div className="card__head">
            <h2>Verification metrics</h2>
          </div>
          {metrics ? (
            <div>
              <div className="stat-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
                <StatCard label="Total verifications" value={metrics.total_verifications} tone="accent" />
                <StatCard label="Genuine" value={metrics.genuine_count} tone="verified" />
                <StatCard label="Suspicious" value={metrics.suspicious_count} tone="suspicious" />
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
                The verification API does not report records with insufficient
                evidence, so that count is omitted here.
              </p>
            </div>
          ) : metricsError ? (
            <EmptyState compact icon="warning" title="Metrics unavailable" message={metricsError} />
          ) : (
            <LoadingState compact label="Loading metrics…" />
          )}
        </div>
      </div>

      <div className="grid grid--2" style={{ gap: 18, marginTop: 18 }}>
        <div className="card">
          <div className="card__head">
            <h2>ML model</h2>
          </div>
          {modelInfo ? (
            <KeyValueGrid>
              <KeyValue label="Model" value={modelInfo.model_name} />
              <KeyValue label="Version" value={modelInfo.model_version} mono />
              <KeyValue label="Feature vector" value={`${modelInfo.features.length} features`} />
              <KeyValue label="Created" value={formatDate(modelInfo.created_at)} />
            </KeyValueGrid>
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>
              Model information is reported by the backend model-info endpoint.
            </p>
          )}
          <div style={{ marginTop: 12 }}>
            <TechnicalDetails label="Model features" defaultOpen={false}>
              <div className="group-list">
                {(modelInfo?.features ?? []).map((f) => (
                  <div key={f} className="group-list__item mono" style={{ fontSize: 12 }}>
                    {f}
                  </div>
                ))}
              </div>
            </TechnicalDetails>
          </div>
        </div>

        <div className="card">
          <div className="card__head">
            <h2>Evidence engine</h2>
          </div>
          <ul className="group-list">
            <li className="group-list__item" style={{ fontSize: 12.5 }}>
              <strong>Evidence fusion:</strong> deterministic fusion of ML
              classification, extraction quality, structure, semantics,
              consistency, PDF forensics, visual analysis, tampering, QR,
              issuer, anomaly and duplicate checks.
            </li>
            <li className="group-list__item" style={{ fontSize: 12.5 }}>
              <strong>External corpus:</strong> disabled by default; enabled
              per verification request via manifest URLs.
            </li>
            <li className="group-list__item" style={{ fontSize: 12.5 }}>
              <strong>Human review:</strong> every case records a reviewer
              decision that is stored alongside — but never overwrites — the
              automated prediction.
            </li>
          </ul>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="card__head">
          <h2>Phase 12 validation report</h2>
          <span className="card__head-sub">
            Documented values — not fetched live from the API
          </span>
        </div>
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>
          The evidence engine was validated against a frozen 30-document
          corpus (27 external + 3 known-difficult). These figures come from{" "}
          <code className="mono">backend/monitoring/phase12_report.json</code>{" "}
          and are not exposed by the live verification API.
        </p>
        <KeyValueGrid>
          <KeyValue label="Corpus size" value="30 documents" />
          <KeyValue label="Decisive results" value="21" />
          <KeyValue label="Accuracy (ML / evidence engine)" value="1.00 / 1.00" />
          <KeyValue label="False positives / negatives" value="0 / 0" />
          <KeyValue label="Known-difficult cases" value="3 (1 routed to manual review)" />
          <KeyValue
            label="Frozen model SHA-256"
            value="e402dca2…4c337"
            mono
          />
        </KeyValueGrid>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <div className="card__head">
          <h2>Raw payloads</h2>
        </div>
        {health ? (
          <div style={{ marginTop: 4 }}>
            <TechnicalDetails label="View health response" defaultOpen={false}>
              <JsonBlock data={health} />
            </TechnicalDetails>
          </div>
        ) : null}
        {modelInfo ? (
          <div style={{ marginTop: 10 }}>
            <TechnicalDetails label="View model info" defaultOpen={false}>
              <JsonBlock data={modelInfo} />
            </TechnicalDetails>
          </div>
        ) : null}
      </div>
    </div>
  );
}