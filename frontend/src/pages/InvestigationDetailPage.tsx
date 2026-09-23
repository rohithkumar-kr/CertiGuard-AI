import { useEffect, useMemo, useState } from "react";
import { Link, useRouter } from "../router/Router";
import { ApiError, getVerificationDetail } from "../services/api";
import type { VerificationDetail } from "../types";
import { formatDate, formatPercent, formatFileType } from "../utils/format";
import { reviewStatusToCaseStatus, CASE_STATUS_LABELS } from "../utils/status";
import { normalizeResult, type ResultView } from "../utils/result";
import { KeyValue, KeyValueGrid, StatusBadge, RiskMeter } from "../components/ui/DataDisplay";
import { EmptyState, LoadingState } from "../components/ui/Feedback";
import { EvidenceSummary } from "../components/result/EvidenceSummary";
import { ForensicsView } from "../components/result/ForensicsView";
import { IssuerPanel } from "../components/result/IssuerPanel";
import { TamperingPanel } from "../components/result/TamperingPanel";
import { RawAnalysis } from "../components/result/RawAnalysis";
import { AuditTrailPanel } from "../components/investigations/AuditTrailPanel";
import { ReviewFeedback } from "../components/investigations/ReviewFeedback";

type TabId = "overview" | "evidence" | "forensics" | "issuer" | "tampering" | "audit" | "raw";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "evidence", label: "Evidence" },
  { id: "forensics", label: "Forensics" },
  { id: "issuer", label: "Issuer" },
  { id: "tampering", label: "Tampering" },
  { id: "audit", label: "Audit trail" },
  { id: "raw", label: "Raw report" },
];

export function InvestigationDetailPage() {
  const { route, navigate } = useRouter();
  const id = route.params.id ?? "";
  const tabId = (route.params.tab as TabId) ?? "overview";

  const [detail, setDetail] = useState<VerificationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const activeTab: TabId = TABS.some((t) => t.id === tabId) ? tabId : "overview";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getVerificationDetail(id)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "Failed to load this investigation.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  const view = useMemo<ResultView | null>(() => (detail ? normalizeResult(detail) : null), [detail]);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [id, activeTab]);

  if (loading) {
    return (
      <div className="card">
        <LoadingState label="Loading investigation…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <EmptyState
          icon="warning"
          title="Investigation unavailable"
          message={error}
        />
        <div style={{ marginTop: 12 }}>
          <Link to="/investigations" className="btn btn--accent">
            Back to investigations
          </Link>
        </div>
      </div>
    );
  }

  if (!detail || !view) {
    return (
      <div className="card">
        <EmptyState icon="document" title="Investigation not found" message="This case could not be found." />
      </div>
    );
  }

  const status = reviewStatusToCaseStatus(detail.review_status);
  const quality = detail.intelligence?.quality_indicators ?? {};

  return (
    <div>
      <Link to="/investigations" className="back-link">
        ← Back to investigations
      </Link>

      <div className="invest-head">
        <div className="invest-head__main">
          <div className="invest-head__row">
            <h1 className="mono" style={{ fontSize: 18 }}>{detail.verification_id}</h1>
            {status ? <StatusBadge status={status} /> : <span className="badge badge--neutral">Unknown</span>}
          </div>
          <p className="muted" style={{ fontSize: 13 }}>
            {detail.filename ?? "Unnamed document"} · verified {formatDate(detail.created_at)}
          </p>
        </div>
        <div className="invest-head__meta">
          <RiskMeter value={detail.risk_score} />
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Investigation sections" style={{ marginTop: 20 }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            className={`tabs__tab${activeTab === t.id ? " tabs__tab--active" : ""}`}
            onClick={() => navigate(`/investigations/${id}${t.id === "overview" ? "" : `/${t.id}`}`)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ marginTop: 20 }}>
        {activeTab === "overview" ? (
          <div className="grid" style={{ gap: 18 }}>
            <div className="card">
              <div className="card__head">
                <h2>Case summary</h2>
              </div>
              <KeyValueGrid>
                <KeyValue label="Prediction" value={status ? CASE_STATUS_LABELS[status] : "—"} />
                <KeyValue label="Risk score" value={formatPercent(detail.risk_score)} />
                <KeyValue label="Review status" value={detail.review_status ?? "—"} />
                <KeyValue label="Cert type" value={detail.certificate_type ?? "—"} />
                <KeyValue label="Issuer" value={detail.issuer ?? "—"} muted={!detail.issuer} />
                <KeyValue label="File type" value={formatFileType(detail.filename)} />
                <KeyValue label="Timestamp" value={formatDate(detail.created_at)} />
                <KeyValue label="Case ID" value={detail.verification_id} mono />
              </KeyValueGrid>
            </div>

            <div className="card">
              <div className="card__head">
                <h2>Analysis notes</h2>
              </div>
              <ul className="group-list">
                <li className="group-list__item" style={{ fontSize: 12.5 }}>
                  <strong>Blank document:</strong> {quality.blank_document ? "Yes" : "No"}
                </li>
                <li className="group-list__item" style={{ fontSize: 12.5 }}>
                  <strong>OCR failed:</strong> {quality.ocr_failed ? "Yes" : "No"}
                </li>
                <li className="group-list__item" style={{ fontSize: 12.5 }}>
                  <strong>Extraction confidence:</strong>{" "}
                  {quality.extraction_confidence != null ? formatPercent(quality.extraction_confidence) : "—"}
                </li>
                <li className="group-list__item" style={{ fontSize: 12.5 }}>
                  <strong>Structure completeness:</strong>{" "}
                  {detail.intelligence?.structure_completeness != null
                    ? formatPercent(detail.intelligence.structure_completeness)
                    : "—"}
                </li>
                <li className="group-list__item" style={{ fontSize: 12.5 }}>
                  <strong>Text extraction quality:</strong> {quality.text_extraction_quality ?? "—"}
                </li>
              </ul>
            </div>

            <div className="card">
              <div className="card__head">
                <h2>Extracted identity</h2>
              </div>
              <KeyValueGrid>
                {Object.entries(detail.intelligence?.identity ?? {}).map(([key, field]) => (
                  <KeyValue key={key} label={field.label ?? key} value={field.value ?? "—"} muted={!field.present} />
                ))}
              </KeyValueGrid>
            </div>

            <ReviewFeedback
              verificationId={detail.verification_id}
              currentLabel={detail.reviewer_label}
              currentNote={detail.reviewer_note}
            />
          </div>
        ) : null}

        {activeTab === "evidence" ? (
          <EvidenceSummary result={view} />
        ) : null}

        {activeTab === "forensics" ? (
          <div className="card">
            <ForensicsView result={view} previewUrl={null} />
          </div>
        ) : null}

        {activeTab === "issuer" ? (
          <IssuerPanel result={view} />
        ) : null}

        {activeTab === "tampering" ? (
          <TamperingPanel result={view} />
        ) : null}

        {activeTab === "audit" ? (
          <AuditTrailPanel verificationId={detail.verification_id} />
        ) : null}

        {activeTab === "raw" ? (
          <div className="card">
            <RawAnalysis result={view} raw={detail} />
          </div>
        ) : null}
      </div>
    </div>
  );
}