import { useEffect, useMemo, useState } from "react";
import { ApiError, getVerifications } from "../services/api";
import type { VerificationRecord } from "../types";
import { PageHeader } from "../components/layout/AppShell";
import { InvestigationTable } from "../components/investigations/InvestigationTable";
import { EmptyState } from "../components/ui/Feedback";

type TabKey = "all" | "verified" | "requires" | "suspicious" | "insufficient";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "all", label: "All cases" },
  { key: "verified", label: "Verified" },
  { key: "requires", label: "Requires Verification" },
  { key: "suspicious", label: "Suspicious" },
  { key: "insufficient", label: "Insufficient Evidence" },
];

export function InvestigationsPage() {
  const [records, setRecords] = useState<VerificationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<TabKey>("all");
  const [issuer, setIssuer] = useState("");
  const [certType, setCertType] = useState("");
  const [sort, setSort] = useState("newest");
  const [limit, setLimit] = useState("20");
  const [querySeq, setQuerySeq] = useState(0);

  const runQuery = () => setQuerySeq((s) => s + 1);

  const params = useMemo(
    () => ({
      limit: Number(limit),
      search: search.trim() || undefined,
      issuer: issuer.trim() || undefined,
      certificateType: certType || undefined,
      sort: sort as "newest" | "oldest",
      reviewStatus:
        tab === "verified" ? "low_risk" : tab === "requires" ? "manual_review" : undefined,
      prediction: tab === "suspicious" ? "suspicious" : undefined,
    }),
    [search, issuer, certType, sort, limit, tab],
  );

  useEffect(() => {
    if (tab === "insufficient") {
      setRecords([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getVerifications(params)
      .then((data) => {
        if (!cancelled) setRecords(data);
      })
      .catch((e) => {
        if (!cancelled) {
          setRecords([]);
          setError(e instanceof ApiError ? e.message : "Failed to load investigations.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params, querySeq, tab]);

  return (
    <div>
      <PageHeader
        title="Investigations"
        subtitle="Review every verification case, the evidence behind each decision, and the human review status."
      />

      <div className="card">
        <div className="filter-bar">
          <label className="field">
            <span className="field__label">Search</span>
            <input
              type="search"
              className="input"
              placeholder="Case ID, file name, hash…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runQuery();
              }}
            />
          </label>
          <label className="field">
            <span className="field__label">Issuer</span>
            <input
              type="text"
              className="input"
              placeholder="e.g. Acme University"
              value={issuer}
              onChange={(e) => setIssuer(e.target.value)}
            />
          </label>
          <label className="field">
            <span className="field__label">Certificate type</span>
            <select className="input" value={certType} onChange={(e) => setCertType(e.target.value)}>
              <option value="">Any</option>
              <option value="academic">Academic</option>
              <option value="professional">Professional</option>
              <option value="government">Government</option>
            </select>
          </label>
          <label className="field">
            <span className="field__label">Sort</span>
            <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
            </select>
          </label>
          <label className="field">
            <span className="field__label">Limit</span>
            <select className="input" value={limit} onChange={(e) => setLimit(e.target.value)}>
              <option value="10">10</option>
              <option value="20">20</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <div className="filter-bar__actions">
            <button type="button" className="btn btn--accent" onClick={runQuery}>
              Apply filters
            </button>
          </div>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Filter investigations by status" style={{ marginTop: 18 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`tabs__tab${tab === t.key ? " tabs__tab--active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "insufficient" ? (
        <div className="card" style={{ marginTop: 18 }}>
          <EmptyState
            icon="document"
            title="No insufficient-evidence filter"
            message="The verification API does not report records whose evidence was insufficient. This view is intentionally empty rather than showing misleading data. Verifications that could not be decided are still recorded and are visible under their own prediction."
          />
        </div>
      ) : (
        <div style={{ marginTop: 18 }}>
          <InvestigationTable records={records} loading={loading} error={error} />
        </div>
      )}
    </div>
  );
}