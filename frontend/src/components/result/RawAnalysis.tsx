import type { ResultView } from "../../utils/result";
import { JsonBlock, TechnicalDetails } from "../ui/TechnicalDetails";

export function RawAnalysis({ result, raw }: { result: ResultView; raw: unknown }) {
  return (
    <div className="raw-analysis">
      <p className="section-description">
        Raw analysis returned by the verification backend. Technical fields are
        provided for auditability and are not interpreted as an additional decision.
      </p>
      <TechnicalDetails label="Raw analysis">
        <JsonBlock data={raw} />
      </TechnicalDetails>
      <div className="raw-analysis__secondary">
        <TechnicalDetails label="Extracted text and identity">
          <JsonBlock data={result.intelligence} />
        </TechnicalDetails>
      </div>
    </div>
  );
}
