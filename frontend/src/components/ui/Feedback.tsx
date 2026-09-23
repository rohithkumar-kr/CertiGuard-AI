import type { ReactNode } from "react";

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {path}
    </svg>
  );
}

/* ---------- Empty state ---------- */

export function EmptyState({
  title,
  message,
  icon = "document",
  actions,
  compact,
}: {
  title: string;
  message: string;
  icon?: "document" | "search" | "warning" | "shield" | "database";
  actions?: ReactNode;
  compact?: boolean;
}) {
  const paths: Record<string, string> = {
    document:
      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
    search:
      '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    warning:
      '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    shield:
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    database:
      '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  };
  return (
    <div
      className={`state${compact ? " state--compact" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="state__icon">
        <Icon path={paths[icon] ?? paths.document} />
      </div>
      <div>
        <p className="state__title">{title}</p>
        <p className="state__message">{message}</p>
      </div>
      {actions ? <div className="state__actions">{actions}</div> : null}
    </div>
  );
}

/* ---------- Loading state ---------- */

export function LoadingState({
  label = "Loading…",
  compact,
}: {
  label?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={`state${compact ? " state--compact" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="spinner spinner--lg" aria-hidden="true" />
      <p className="state__title">{label}</p>
    </div>
  );
}

export function LoadingLine({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="loading-line" role="status">
      <span className="spinner spinner--sm" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

/* ---------- Error state ---------- */

export function ErrorState({
  title = "Could not load data",
  message,
  onRetry,
  compact,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className={`state${compact ? " state--compact" : ""}`} role="alert">
      <div className="state__icon state__icon--error">
        <Icon path='<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>' />
      </div>
      <div>
        <p className="state__title">{title}</p>
        <p className="state__message">{message}</p>
      </div>
      {onRetry ? (
        <div className="state__actions">
          <button type="button" className="btn btn--primary" onClick={onRetry}>
            Try again
          </button>
        </div>
      ) : null}
    </div>
  );
}

/* ---------- Inline alert ---------- */

export function Alert({
  tone = "info",
  children,
}: {
  tone?: "info" | "warn" | "error" | "success";
  children: ReactNode;
}) {
  return (
    <div className={`alert alert--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}