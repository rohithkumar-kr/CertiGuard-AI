import { evidenceToCaseStatus, ASSESSMENT_LABELS } from "../../utils/status";
import type { CaseStatus } from "../../utils/status";
import type { ResultView } from "../../utils/result";
import { formatDate, formatPercent } from "../../utils/format";
import { ConfidenceIndicator, RiskMeter, StatusBadge } from "../ui/DataDisplay";
import { CERT_TYPE_LABELS } from "../../utils/status";

export function DecisionCard({ result }: { result: ResultView }) {
  const status: CaseStatus =
    evidenceToCaseStatus(result.evidence) ?? (result.prediction === "genuine" ? "verified" : result.prediction === "error" ? "error" : "suspicious");

  const assessmentTitle = result.evidence
    ? ASSESSMENT_LABELS[result.evidence.assessment] ?? result.evidence.assessment
    : result.prediction === "genuine"
      ? "Verified"
      : "Suspicious";

  const sub =
    result.evidence?.assessment === "LIKELY_GENUINE"
      ? "Independent evidence across ML classification, document forensics, issuer verification and tampering analysis supports this document."
      : result.evidence?.assessment === "LIKELY_SUSPICIOUS"
        ? "Multiple independent evidence sources indicate the document should not be trusted without human review."
        : result.evidence?.assessment === "REQUIRES_VERIFICATION"
          ? "The evidence is contradictory or incomplete. Manual review is required before relying on this document."
          : result.evidence?.assessment === "INSUFFICIENT_EVIDENCE"
            ? "There is not enough extractable evidence to form a reliable assessment. Manual review is required."
            : result.prediction === "genuine"
              ? "The ML classifier found no strong fraud-risk signals. This is a preliminary assessment, not a legal authentication."
              : "The ML classifier detected fraud-risk signals. This is a preliminary assessment and requires human review.";

  const primaryType =
    result.intelligence?.certificate_type?.primary ?? "unknown";
  const certTypeLabel = CERT_TYPE_LABELS[primaryType] ?? primaryType;

  return (
    <div
      className={`decision decision--${status}`}
      role="status"
      aria-live="polite"
    >
      <div className="decision__inner">
        <div>
          <p className="decision__eyebrow">Final verification result</p>
          <h2 className="decision__title">{assessmentTitle}</h2>
          <p className="decision__sub">{sub}</p>
          <div className="decision__meta">
            <StatusBadge status={status} label={assessmentTitle} />
            {result.issuer ? (
              <span className="badge badge--neutral">Issuer: {result.issuer}</span>
            ) : null}
            {result.duplicate.is_duplicate ? (
              <span className="badge badge--requires_verification">
                Duplicate detected
              </span>
            ) : null}
          </div>
        </div>

        <div className="decision__right">
          {result.evidence?.confidence !== undefined ? (
            <ConfidenceIndicator
              value={result.evidence.confidence}
              tone={status === "verified" ? "verified" : status === "suspicious" ? "suspicious" : status === "requires_verification" ? "requires_verification" : "neutral"}
            />
          ) : (
            <ConfidenceIndicator value={result.confidence} tone="accent" />
          )}
          <RiskMeter value={result.riskScore} />
          <div className="decision__facts">
            <div className="decision__fact">
              <span className="decision__fact-label">Model</span>
              <span className="decision__fact-value mono">{result.modelVersion}</span>
            </div>
            <div className="decision__fact">
              <span className="decision__fact-label">Certificate type</span>
              <span className="decision__fact-value">{certTypeLabel}</span>
            </div>
            <div className="decision__fact">
              <span className="decision__fact-label">Risk score</span>
              <span className="decision__fact-value">{formatPercent(result.riskScore)}</span>
            </div>
            <div className="decision__fact">
              <span className="decision__fact-label">Verification</span>
              <span className="decision__fact-value mono">{result.verificationId}</span>
            </div>
            {result.createdAt ? (
              <div className="decision__fact">
                <span className="decision__fact-label">Analyzed</span>
                <span className="decision__fact-value">{formatDate(result.createdAt)}</span>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}