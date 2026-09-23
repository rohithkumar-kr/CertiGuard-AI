import { useState, type ReactNode } from "react";

export interface TabDef {
  id: string;
  label: string;
  content: ReactNode;
}

export function Tabs({
  tabs,
  initialId,
  ariaLabel,
}: {
  tabs: TabDef[];
  initialId?: string;
  ariaLabel: string;
}) {
  const [active, setActive] = useState(
    tabs.some((t) => t.id === initialId) ? initialId! : tabs[0]?.id,
  );
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  if (!current) return null;

  return (
    <div>
      <div className="tabs" role="tablist" aria-label={ariaLabel}>
        {tabs.map((tab) => {
          const selected = tab.id === current.id;
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              role="tab"
              aria-selected={selected}
              aria-controls={`panel-${tab.id}`}
              className={`tab-btn${selected ? " tab-btn--active" : ""}`}
              onClick={() => setActive(tab.id)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        id={`panel-${current.id}`}
        role="tabpanel"
        aria-labelledby={`tab-${current.id}`}
        className="tab-panel"
      >
        {current.content}
      </div>
    </div>
  );
}