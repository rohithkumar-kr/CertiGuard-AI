import type { ReactNode } from "react";
import type { ResultView } from "../../utils/result";
import { DecisionCard } from "./DecisionCard";
import { EvidenceSummary } from "./EvidenceSummary";
import { EvidenceFindings } from "./EvidenceFindings";
import { ExplainabilityCard } from "./ExplainabilityCard";
import { FusionDiagram } from "./FusionDiagram";
import { ForensicsView } from "./ForensicsView";
import { IssuerPanel } from "./IssuerPanel";
import { TamperingPanel } from "./TamperingPanel";
import { RawAnalysis } from "./RawAnalysis";
import { VerificationHeader } from "./VerificationHeader";

export function ResultWorkspace({
  result,
  previewUrl = null,
  mediaType = null,
  raw,
  actions,
}: {
  result: ResultView;
  previewUrl?: string | null;
  mediaType?: string | null;
  raw: unknown;
  actions?: ReactNode;
}) {
  return (
    <div className="result-report">
      <VerificationHeader result={result} actions={actions} />

      <section className="report-section report-section--decision" aria-labelledby="decision-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Decision</p>
            <h2 id="decision-title">Final verification result</h2>
          </div>
        </div>
        <DecisionCard result={result} />
        <ExplainabilityCard result={result} />
      </section>

      <section className="report-section" aria-labelledby="evidence-summary-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Overview</p>
            <h2 id="evidence-summary-title">Evidence summary</h2>
            <p className="section-head__sub">
              Independent evidence sources returned for this verification
            </p>
          </div>
        </div>
        <EvidenceSummary result={result} />
      </section>

      <section className="report-section" aria-labelledby="evidence-findings-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Review trail</p>
            <h2 id="evidence-findings-title">Evidence findings</h2>
            <p className="section-head__sub">Backend findings, preserved with their returned explanations</p>
          </div>
        </div>
        <EvidenceFindings result={result} />
      </section>

      <section className="report-section" aria-labelledby="fusion-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Decision context</p>
            <h2 id="fusion-title">How the decision was produced</h2>
            <p className="section-head__sub">Evidence contributors and the resulting final assessment</p>
          </div>
        </div>
        <FusionDiagram result={result} />
      </section>

      <section className="report-section" aria-labelledby="forensics-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Document examination</p>
            <h2 id="forensics-title">Digital forensics</h2>
            <p className="section-head__sub">Preview and forensic findings returned by the backend</p>
          </div>
        </div>
        <ForensicsView result={result} previewUrl={previewUrl} mediaType={mediaType} />
        <TamperingPanel result={result} />
      </section>

      <section className="report-section report-section--issuer" aria-labelledby="issuer-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">External context</p>
            <h2 id="issuer-title">Issuer verification</h2>
            <p className="section-head__sub">Issuer registry and verification-service result</p>
          </div>
        </div>
        <IssuerPanel result={result} />
      </section>

      <section className="report-section report-section--technical" aria-labelledby="raw-title">
        <div className="section-head">
          <div>
            <p className="section-kicker">Audit data</p>
            <h2 id="raw-title">Technical details</h2>
            <p className="section-head__sub">Raw analysis returned by the verification backend</p>
          </div>
        </div>
        <RawAnalysis result={result} raw={raw} />
      </section>
    </div>
  );
}
