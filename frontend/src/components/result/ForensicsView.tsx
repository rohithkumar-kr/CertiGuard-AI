import { useEffect, useState } from "react";
import type { ResultView } from "../../utils/result";
import { buildForensicFindings } from "../../utils/forensics";
import { SeverityBadge } from "../ui/DataDisplay";
import { EmptyState } from "../ui/Feedback";

/** Preview the uploaded document via an in-memory object URL (fresh verify). */
export function useObjectPreview(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);
  return url;
}

export function DocumentPreview({
  previewUrl,
  filename,
}: {
  previewUrl: string | null;
  filename: string | null;
}) {
  const isPdf = previewUrl && /\.pdf$/i.test(filename ?? "");
  const isImage = previewUrl && !isPdf;
  const ext = filename?.split(".").pop()?.toUpperCase() ?? "FILE";

  return (
    <div className="doc-preview">
      <div className="doc-preview__frame">
        {isImage ? (
          <img src={previewUrl!} alt={`Preview of ${filename}`} className="doc-preview__img" />
        ) : isPdf ? (
          <iframe
            src={`${previewUrl}#toolbar=0&view=FitH`}
            title={`Preview of ${filename}`}
            style={{ width: "100%", height: "520px", border: "none", borderRadius: "var(--radius-sm)" }}
          />
        ) : (
          <div className="doc-preview__placeholder">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5" />
              <path d="M9 13h6M9 17h4" />
            </svg>
            <div>
              <strong>No preview available</strong>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                The persisted case does not expose the original document
                through the verification API.
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="doc-preview__bar">
        <span title={filename ?? undefined}>{filename ?? "Unnamed document"}</span>
        <span className="mono">{ext}</span>
      </div>
    </div>
  );
}

export function ForensicsView({
  result,
  previewUrl,
}: {
  result: ResultView;
  previewUrl: string | null;
}) {
  const findings = buildForensicFindings(result);
  const severityOrder = { high: 0, medium: 1, low: 2, critical: -1 } as const;
  const sorted = [...findings].sort((a, b) => {
    const sa = a.severity in severityOrder ? severityOrder[a.severity as keyof typeof severityOrder] : 3;
    const sb = b.severity in severityOrder ? severityOrder[b.severity as keyof typeof severityOrder] : 3;
    return sa - sb;
  });

  return (
    <div>
      <div className="forensics-grid">
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Document</h3>
          <DocumentPreview previewUrl={previewUrl} filename={result.filename} />
        </div>
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Forensic findings</h3>
          {sorted.length === 0 ? (
            <EmptyState
              compact
              icon="shield"
              title="No forensic findings"
              message="No explicit forensic findings were recorded for this document. The evidence below reflects what the backend reported."
            />
          ) : (
            <div className="finding-list">
              {sorted.map((f) => (
                <div className="finding" key={f.id}>
                  <span
                    className="finding__icon"
                    aria-hidden="true"
                    style={{
                      color:
                        f.severity === "high" || f.severity === "critical"
                          ? "var(--red)"
                          : f.severity === "medium"
                            ? "var(--amber)"
                            : "var(--blue)",
                    }}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                    </svg>
                  </span>
                  <div className="finding__body">
                    <div className="finding__head">
                      <span className="finding__label">{f.label}</span>
                      <SeverityBadge severity={f.severity} />
                    </div>
                    <span className="muted" style={{ fontSize: 11, display: "block", marginTop: 2 }}>
                      {f.group}
                    </span>
                    {f.detail ? (
                      <p className="finding__detail">{f.detail}</p>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}