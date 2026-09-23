import type { ResultView } from "../../utils/result";
import { DecisionCard } from "./DecisionCard";
import { EvidenceSummary } from "./EvidenceSummary";
import { ExplainabilityCard } from "./ExplainabilityCard";
import { FusionDiagram } from "./FusionDiagram";
import { ForensicsView } from "./ForensicsView";
import { IssuerPanel } from "./IssuerPanel";
import { TamperingPanel } from "./TamperingPanel";
import { RawAnalysis } from "./RawAnalysis";

/**
 * Composed result experience used by both the verify workspace and the
 * investigation detail page. The `raw` object is the unmodified backend
 * response used by the Raw Analysis tab.
 */
export function ResultWorkspace({
  result,
  previewUrl = null,
  raw,
}: {
  result: ResultView;
  previewUrl?: string | null;
  raw: unknown;
}) {
  return (
    <div className="grid" style={{ gap: 18 }}>
      <DecisionCard result={result} />

      <section aria-labelledby="evidence-summary-title">
        <div className="section-head">
          <h2 id="evidence-summary-title">Evidence summary</h2>
          <span className="section-head__sub">
            Independent evidence sources behind the decision
          </span>
        </div>
        <EvidenceSummary result={result} />
      </section>

      <ExplainabilityCard result={result} />

      <section aria-labelledby="fusion-title">
        <div className="section-head">
          <h2 id="fusion-title">How the decision was fused</h2>
          <span className="section-head__sub">
            ML classification · forensics · issuer · tampering — combined
          </span>
        </div>
        <FusionDiagram result={result} />
      </section>

      <section aria-labelledby="forensics-title">
        <div className="section-head">
          <h2 id="forensics-title">Digital forensics</h2>
          <span className="section-head__sub">
            Document examination findings
          </span>
        </div>
        <ForensicsView result={result} previewUrl={previewUrl} />
      </section>

      <div className="grid grid--2">
        <IssuerPanel result={result} />
        <TamperingPanel result={result} />
      </div>

      <section aria-labelledby="raw-title">
        <div className="section-head">
          <h2 id="raw-title">Technical details</h2>
        </div>
        <RawAnalysis result={result} raw={raw} />
      </section>
    </div>
  );
}