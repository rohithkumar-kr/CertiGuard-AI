import { useState, type CSSProperties, type ReactNode } from "react";

export function TechnicalDetails({
  label,
  children,
  defaultOpen,
  style,
}: {
  label?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  style?: CSSProperties;
}) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  return (
    <details
      className="tech-details"
      style={style}
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="tech-details__summary">
        <span>{label ?? "View Raw Analysis"}</span>
        <svg
          className="tech-details__chevron"
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </summary>
      <div className="tech-details__body">{children}</div>
    </details>
  );
}

export function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre>{JSON.stringify(data, null, 2)}</pre>
  );
}