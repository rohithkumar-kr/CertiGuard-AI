import type { ResultView } from "../../utils/result";
import { JsonBlock, TechnicalDetails } from "../ui/TechnicalDetails";

export function RawAnalysis({ result, raw }: { result: ResultView; raw: unknown }) {
  return (
    <div>
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        Raw analysis is provided for technical users and auditors. It reflects
        the exact response returned by the verification backend — nothing is
        derived client-side.
      </p>
      <TechnicalDetails label="View Raw Analysis" defaultOpen>
        <JsonBlock data={raw} />
      </TechnicalDetails>
      <div style={{ marginTop: 14 }}>
        <TechnicalDetails label="Extracted text & identity">
          <JsonBlock data={result.intelligence} />
        </TechnicalDetails>
      </div>
    </div>
  );
}