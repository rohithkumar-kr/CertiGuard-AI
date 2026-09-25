import { useCallback, useEffect, useState } from "react";
import { Link } from "../router/Router";
import { ApiError, getVerificationDetail, verifyCertificate } from "../services/api";
import type { VerificationDetail, VerificationResponse } from "../types";
import { normalizeResult, type ResultView } from "../utils/result";
import { PageHeader } from "../components/layout/AppShell";
import { UploadZone } from "../components/verify/UploadZone";
import { VerificationPipeline } from "../components/verify/VerificationPipeline";
import { ResultWorkspace } from "../components/result/ResultWorkspace";
import { useObjectPreview } from "../components/result/ForensicsView";
import { Alert } from "../components/ui/Feedback";

type Phase = "idle" | "verifying" | "result" | "error";

export function VerifyPage() {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [detail, setDetail] = useState<VerificationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewUrl = useObjectPreview(file);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [phase]);

  const handleVerify = useCallback(async () => {
    if (!file) {
      setError("Please select a certificate file first.");
      return;
    }
    setPhase("verifying");
    setError(null);
    try {
      const response = await verifyCertificate(file);
      setResult(response);
      let detailData: VerificationDetail | null = null;
      try {
        detailData = await getVerificationDetail(response.verification_id);
      } catch {
        // Evidence details are a supplement; the live response still renders.
      }
      setDetail(detailData);
      setPhase("result");
    } catch (e) {
      const message =
        e instanceof ApiError
          ? e.message
          : "Verification failed. Please check the file and try again.";
      setError(message);
      setPhase("error");
    }
  }, [file]);

  const handleReset = useCallback(() => {
    setFile(null);
    setResult(null);
    setDetail(null);
    setError(null);
    setPhase("idle");
  }, []);

  let view: ResultView | null = null;
  let raw: unknown = result;
  if (result) {
    const normalized = normalizeResult(result);
    view = {
      ...normalized,
      filename: detail?.filename ?? file?.name ?? normalized.filename,
      evidenceDetails: detail?.evidence_details ?? normalized.evidenceDetails,
    };
    if (detail) raw = detail;
  }

  return (
    <div>
      <PageHeader
        title="Verify Certificate"
        subtitle="Upload a certificate to run the full analysis pipeline: document ingestion, extraction, ML classification, evidence fusion, issuer verification and forensic checks."
      />

      <div className="card" style={{ marginBottom: 18 }}>
        <UploadZone
          file={file}
          loading={phase === "verifying"}
          onFileChange={(f) => {
            setFile(f);
            setPhase("idle");
            setResult(null);
            setDetail(null);
            setError(null);
          }}
          onVerify={handleVerify}
          error={error}
        />
      </div>

      {phase === "verifying" ? (
        <div className="card" role="status" aria-live="polite">
          <div className="card__head">
            <h2>Analysis in progress</h2>
            <span className="card__head-sub">
              Running document analysis, ML classification, evidence fusion,
              issuer verification and forensic checks
            </span>
          </div>
          <VerificationPipeline status="processing" />
          <div className="loading-line">
            <span className="spinner spinner--sm" aria-hidden="true" />
            <span>
              The backend returns a single complete analysis. Stages advance
              while analysis runs and all complete together when the result
              arrives.
            </span>
          </div>
        </div>
      ) : null}

      {phase === "error" ? (
        <div className="card" role="alert">
          <div className="card__head">
            <h2>Verification failed</h2>
          </div>
          <VerificationPipeline status="error" />
          <div style={{ marginTop: 14 }}>
            <Alert tone="error">
              <span>{error}</span>
            </Alert>
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 12 }}>
            You can try a different file or retry. The failed attempt is
            recorded in the monitoring log.
          </p>
        </div>
      ) : null}

      {phase === "result" && result && view ? (
        <div>
          <VerificationPipeline status="success" ariaMessage="Analysis complete." />
          <div className="result-report__entry">
            <ResultWorkspace
              result={view}
              previewUrl={previewUrl}
              mediaType={file?.type ?? null}
              raw={raw}
              actions={
                <>
                  <Link
                    to={`/investigations/${result.verification_id}`}
                    className="btn btn--ghost"
                  >
                    Open investigation
                  </Link>
                  <button type="button" className="btn btn--primary" onClick={handleReset}>
                    Verify another
                  </button>
                </>
              }
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}