import type { ReactNode } from "react";
import type { ResultView } from "../../utils/result";
import {
  ASSESSMENT_LABELS,
  CASE_STATUS_LABELS,
  resultToCaseStatus,
} from "../../utils/status";
import { formatDate } from "../../utils/format";
import { StatusBadge } from "../ui/DataDisplay";

export function VerificationHeader({
  result,
  actions,
}: {
  result: ResultView;
  actions?: ReactNode;
}) {
  const status = resultToCaseStatus(result);
  const assessment = result.evidence?.assessment;
  const statusLabel = assessment
    ? ASSESSMENT_LABELS[assessment] ?? assessment
    : status
      ? CASE_STATUS_LABELS[status]
      : "Status unavailable";
  const filename =
    typeof result.filename === "string" && result.filename.trim()
      ? result.filename
      : null;

  return (
    <header className="report-header" aria-labelledby="verification-header-title">
      <div className="report-header__identity">
        <p className="report-header__eyebrow">Verification report</p>
        <h1 id="verification-header-title" className="report-header__title">
          Certificate Verification
        </h1>
        {filename ? (
          <p className="report-header__filename" title={filename}>
            {filename}
          </p>
        ) : null}
        <div className="report-header__facts">
          <div className="report-header__fact">
            <span>Verification ID</span>
            <strong className="mono">{result.verificationId}</strong>
          </div>
          {result.createdAt ? (
            <div className="report-header__fact">
              <span>Date and time</span>
              <strong>{formatDate(result.createdAt)}</strong>
            </div>
          ) : null}
          {result.modelVersion ? (
            <div className="report-header__fact">
              <span>Model</span>
              <strong className="mono">{result.modelVersion}</strong>
            </div>
          ) : null}
        </div>
      </div>
      <div className="report-header__aside">
        <StatusBadge status={status ?? "neutral"} label={statusLabel} />
        {actions ? <div className="report-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
