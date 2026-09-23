import { useEffect, useState } from "react";

/**
 * The eight stages of the verification workflow. The backend returns a single
 * response, so this is a progress experience: stages advance visually while
 * analysis is in progress and all complete together when the response arrives.
 * It never claims that individual backend steps finished independently.
 */
export const PIPELINE_STAGES = [
  { id: "ingestion", label: "Document ingestion" },
  { id: "extraction", label: "Text extraction" },
  { id: "features", label: "Feature extraction" },
  { id: "ml", label: "ML analysis" },
  { id: "evidence", label: "Evidence analysis" },
  { id: "issuer", label: "Issuer verification" },
  { id: "tampering", label: "Tampering analysis" },
  { id: "decision", label: "Final decision" },
] as const;

type StageState = "pending" | "active" | "done" | "failed";

const STATUS_COPY: Record<StageState, string> = {
  pending: "Queued",
  active: "In progress",
  done: "Complete",
  failed: "Failed",
};

interface VerificationPipelineProps {
  status: "processing" | "success" | "error";
  /** For screen readers, describe what is actually happening. */
  ariaMessage?: string;
}

export function VerificationPipeline({ status, ariaMessage }: VerificationPipelineProps) {
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (status !== "processing") {
      setActiveIndex(0);
      return;
    }
    setActiveIndex(0);
    const timer = window.setInterval(() => {
      setActiveIndex((i) => Math.min(i + 1, PIPELINE_STAGES.length - 1));
    }, 900);
    return () => window.clearInterval(timer);
  }, [status]);

  const stateFor = (index: number): StageState => {
    if (status === "error") {
      return index === PIPELINE_STAGES.length - 1 ? "failed" : "done";
    }
    if (status === "success") return "done";
    if (index < activeIndex) return "done";
    if (index === activeIndex) return "active";
    return "pending";
  };

  return (
    <div>
      <p className="sr-only" role="status" aria-live="polite">
        {ariaMessage ?? (status === "processing" ? "Analysis in progress." : "Analysis complete.")}
      </p>
      <ol className="pipeline" aria-label="Verification workflow stages">
        {PIPELINE_STAGES.map((stage, index) => {
          const state = stateFor(index);
          return (
            <li
              key={stage.id}
              className={`pipeline__stage pipeline__stage--${state}`}
              aria-current={state === "active" ? "step" : undefined}
            >
              <div className="pipeline__stage-head">
                <span className="pipeline__index" aria-hidden="true">
                  {state === "done" ? "✓" : state === "failed" ? "!" : index + 1}
                </span>
                <span className="pipeline__state-icon" aria-hidden="true">
                  {state === "active" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                      <path d="M12 5v14M5 12h14" />
                    </svg>
                  ) : state === "done" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="m5 12 4 4L19 6" />
                    </svg>
                  ) : state === "failed" ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
                    </svg>
                  )}
                </span>
              </div>
              <span className="pipeline__label">{stage.label}</span>
              <span className="pipeline__status">{STATUS_COPY[state]}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}