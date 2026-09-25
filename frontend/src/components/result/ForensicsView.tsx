import { useEffect, useState } from "react";
import type { ResultView } from "../../utils/result";
import { buildForensicFindings } from "../../utils/forensics";
import { formatFileType } from "../../utils/format";
import { SeverityBadge } from "../ui/DataDisplay";
import { EmptyState } from "../ui/Feedback";

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
  mediaType,
}: {
  previewUrl: string | null;
  filename: string | null;
  mediaType?: string | null;
}) {
  const [previewError, setPreviewError] = useState(false);

  useEffect(() => {
    setPreviewError(false);
  }, [previewUrl, filename, mediaType]);

  const normalizedMediaType = mediaType?.toLowerCase() ?? "";
  const isPdf =
    normalizedMediaType === "application/pdf" || /\.pdf$/i.test(filename ?? "");
  const isImageType =
    normalizedMediaType === "image/jpeg" ||
    normalizedMediaType === "image/png" ||
    /\.(jpe?g|png)$/i.test(filename ?? "");
  const isImage = Boolean(previewUrl) && isImageType;
  const unavailable = !previewUrl || previewError || (!isPdf && !isImage);
  const extension = filename
    ? formatFileType(filename)
    : isPdf
      ? "PDF"
      : normalizedMediaType === "image/png"
        ? "PNG"
        : normalizedMediaType === "image/jpeg"
          ? "JPG"
          : "DOC";
  const documentLabel = filename ?? "Uploaded document";

  return (
    <div className="doc-preview">
      <div className="doc-preview__frame">
        {unavailable ? (
          <div className="doc-preview__placeholder">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5" />
              <path d="M9 13h6M9 17h4" />
            </svg>
            <div>
              <strong>Document preview unavailable</strong>
              <div className="muted">
                The document preview could not be loaded for this verification.
              </div>
            </div>
          </div>
        ) : isImage ? (
          <img
            src={previewUrl!}
            alt={`Preview of ${documentLabel}`}
            className="doc-preview__img"
            onError={() => setPreviewError(true)}
          />
        ) : (
          <iframe
            src={`${previewUrl}#toolbar=0&view=FitH`}
            title={`Preview of ${documentLabel}`}
            className="doc-preview__pdf"
            onLoad={() => setPreviewError(false)}
            onError={() => setPreviewError(true)}
          />
        )}
      </div>
      {previewUrl && !previewError ? (
        <div className="doc-preview__bar">
          <span title={filename ?? undefined}>{documentLabel}</span>
          <span className="mono">{extension}</span>
        </div>
      ) : null}
    </div>
  );
}

export function ForensicsView({
  result,
  previewUrl,
  mediaType,
}: {
  result: ResultView;
  previewUrl: string | null;
  mediaType?: string | null;
}) {
  const findings = buildForensicFindings(result);
  const severityOrder = { critical: 0, high: 1, medium: 2, low: 3, unknown: 4 } as const;
  const sorted = [...findings].sort((a, b) => {
    const sa = severityOrder[a.severity];
    const sb = severityOrder[b.severity];
    return sa - sb;
  });

  return (
    <div className="forensics-grid">
      <section className="forensics-column forensics-column--preview">
        <h3>Document preview</h3>
        <DocumentPreview
          previewUrl={previewUrl}
          filename={result.filename}
          mediaType={mediaType}
        />
      </section>
      <section className="forensics-column forensics-column--findings">
        <h3>Forensic findings</h3>
        {sorted.length === 0 ? (
          <EmptyState
            compact
            icon="shield"
            title="No forensic findings"
            message="No explicit forensic findings were recorded for this document."
          />
        ) : (
          <div className="finding-list">
            {sorted.map((finding) => (
              <div className="finding" key={finding.id}>
                <span
                  className="finding__icon"
                  aria-hidden="true"
                  data-severity={finding.severity}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                </span>
                <div className="finding__body">
                  <div className="finding__head">
                    <span className="finding__label">{finding.label}</span>
                    <SeverityBadge severity={finding.severity} />
                  </div>
                  <span className="finding__group">{finding.group}</span>
                  {finding.detail ? (
                    <p className="finding__detail">{finding.detail}</p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
