import {
  ASSESSMENT_LABELS,
  CASE_STATUS_LABELS,
  resultToCaseStatus,
} from "../../utils/status";
import type { CaseStatus } from "../../utils/status";
import type { ResultView } from "../../utils/result";
import { formatDate, formatPercent } from "../../utils/format";
import { ConfidenceIndicator, RiskMeter, StatusBadge } from "../ui/DataDisplay";
import { CERT_TYPE_LABELS } from "../../utils/status";

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function DecisionCard({ result }: { result: ResultView }) {
  const status: CaseStatus =
    resultToCaseStatus(result) ??
    (result.prediction === "genuine"
      ? "verified"
      : result.prediction === "error"
        ? "error"
        : "requires_verification");
  const assessment = result.evidence?.assessment;
  const assessmentTitle = assessment
    ? ASSESSMENT_LABELS[assessment] ?? assessment
    : CASE_STATUS_LABELS[status];
  const explanation =
    result.message?.trim() ||
    (result.evidence?.assessment === "LIKELY_GENUINE"
      ? "Independent evidence across ML classification, document forensics, issuer verification and tampering analysis supports this document."
      : result.evidence?.assessment === "LIKELY_SUSPICIOUS"
        ? "Multiple independent evidence sources indicate the document should not be trusted without human review."
        : result.evidence?.assessment === "REQUIRES_VERIFICATION"
          ? "The evidence is contradictory or incomplete. Manual review is required before relying on this document."
          : result.evidence?.assessment === "INSUFFICIENT_EVIDENCE"
            ? "There is not enough extractable evidence to form a reliable assessment. Manual review is required."
            : result.prediction === "genuine"
              ? "The ML classifier found no strong fraud-risk signals. This is a preliminary assessment, not a legal authentication."
              : result.prediction === "error"
                ? "The backend reported an error for this verification. A final assessment could not be completed."
                : "The ML prediction could not be mapped to a final assessment. Manual review is required.");
  const riskScore = finiteNumber(result.riskScore);
  const confidence = finiteNumber(result.evidence?.confidence) ?? finiteNumber(result.confidence);
  const recommendation = result.recommendedAction;
  const recommendationHeading = recommendation?.heading?.trim();
  const recommendationMessage = recommendation?.message?.trim();
  const primaryType = result.intelligence?.certificate_type?.primary;
  const certTypeLabel = primaryType
    ? CERT_TYPE_LABELS[primaryType] ?? primaryType
    : null;

  return (
    <div
      className={`decision decision--${status}`}
      role="status"
      aria-live="polite"
    >
      <div className="decision__inner">
        <div className="decision__main">
          <p className="decision__eyebrow">Final verification result</p>
          <h2 className="decision__title">{assessmentTitle}</h2>
          <div className="decision__explanation">
            <span className="decision__explanation-label">Explanation</span>
            <p>{explanation}</p>
          </div>
          {recommendationHeading || recommendationMessage ? (
            <div className="decision__recommendation">
              <span className="decision__recommendation-label">
                Review recommendation
              </span>
              {recommendationHeading ? <strong>{recommendationHeading}</strong> : null}
              {recommendationMessage ? <p>{recommendationMessage}</p> : null}
            </div>
          ) : null}
          <div className="decision__meta">
            <StatusBadge status={status} label={assessmentTitle} />
            {result.duplicate?.is_duplicate ? (
              <span className="badge badge--requires_verification">
                Duplicate detected
              </span>
            ) : null}
            {result.issuer ? (
              <span className="decision__issuer">Issuer: {result.issuer}</span>
            ) : null}
          </div>
        </div>

        <div className="decision__right">
          {confidence !== null ? (
            <ConfidenceIndicator
              value={confidence}
              tone={
                status === "verified"
                  ? "verified"
                  : status === "suspicious"
                    ? "suspicious"
                    : status === "requires_verification"
                      ? "requires_verification"
                      : "neutral"
              }
            />
          ) : null}
          {riskScore !== null ? <RiskMeter value={riskScore} /> : null}
          <div className="decision__facts">
            {result.modelVersion ? (
              <div className="decision__fact">
                <span className="decision__fact-label">Model</span>
                <span className="decision__fact-value mono">
                  {result.modelVersion}
                </span>
              </div>
            ) : null}
            {certTypeLabel ? (
              <div className="decision__fact">
                <span className="decision__fact-label">Certificate type</span>
                <span className="decision__fact-value">{certTypeLabel}</span>
              </div>
            ) : null}
            {riskScore !== null ? (
              <div className="decision__fact">
                <span className="decision__fact-label">Risk score</span>
                <span className="decision__fact-value">{formatPercent(riskScore)}</span>
              </div>
            ) : null}
            <div className="decision__fact">
              <span className="decision__fact-label">Verification</span>
              <span className="decision__fact-value mono">
                {result.verificationId}
              </span>
            </div>
            {result.createdAt ? (
              <div className="decision__fact">
                <span className="decision__fact-label">Analyzed</span>
                <span className="decision__fact-value">
                  {formatDate(result.createdAt)}
                </span>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
