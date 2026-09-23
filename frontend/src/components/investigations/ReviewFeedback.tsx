import { useState } from "react";
import { ApiError, submitFeedback } from "../../services/api";
import type { ReviewerLabel } from "../../types";
import { Alert } from "../ui/Feedback";

const OPTIONS: Array<{ value: ReviewerLabel; label: string }> = [
  { value: "confirmed_genuine", label: "Confirmed genuine" },
  { value: "uncertain", label: "Uncertain" },
  { value: "confirmed_suspicious", label: "Confirmed suspicious" },
];

export function ReviewFeedback({
  verificationId,
  currentLabel,
  currentNote,
  onSaved,
}: {
  verificationId: string;
  currentLabel?: ReviewerLabel | null;
  currentNote?: string | null;
  onSaved?: (label: ReviewerLabel, note: string) => void;
}) {
  const [label, setLabel] = useState<ReviewerLabel | null>(currentLabel ?? null);
  const [notes, setNotes] = useState(currentNote ?? "");
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ ok: boolean; message: string } | null>(null);

  const handleSubmit = async () => {
    if (!label) return;
    setSaving(true);
    setFeedback(null);
    try {
      await submitFeedback(verificationId, label, notes);
      setFeedback({ ok: true, message: "Review decision saved. It does not alter the ML prediction or risk score." });
      onSaved?.(label, notes);
    } catch (e) {
      setFeedback({
        ok: false,
        message: e instanceof ApiError ? e.message : "Failed to save the review decision.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card">
      <div className="card__head">
        <h2>Human review</h2>
        <span className="card__head-sub">
          Records a reviewer decision for this case
        </span>
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        Human review never modifies the ML model, the prediction, or the risk
        score. One decision per verification.
      </p>
      <div className="field">
        <span className="field__label">Reviewer decision</span>
        <div className="btn-group">
          {OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              className={`btn btn--sm ${label === o.value ? "btn--accent" : "btn--ghost"}`}
              aria-pressed={label === o.value}
              onClick={() => setLabel(o.value)}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
      <label className="field" style={{ marginTop: 12 }}>
        <span className="field__label">Notes</span>
        <textarea
          className="input"
          rows={3}
          placeholder="Optional notes about this case…"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!label || saving}
          onClick={handleSubmit}
        >
          {saving ? "Saving…" : "Save review"}
        </button>
        {feedback ? (
          <span role="status" style={{ fontSize: 12.5, color: feedback.ok ? "var(--green)" : "var(--red)" }}>
            {feedback.message}
          </span>
        ) : null}
      </div>
      {currentLabel ? (
        <div style={{ marginTop: 12 }}>
          <Alert tone="info">
            This case was already reviewed as "{currentLabel}"
            {currentNote ? ` with note: "${currentNote}"` : ""}.
          </Alert>
        </div>
      ) : null}
    </div>
  );
}