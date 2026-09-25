import { useEffect, useState, type ReactNode } from "react";
import { useUser } from "@clerk/clerk-react";
import { Link, useRouter } from "../../router/Router";
import type { HealthResponse } from "../../types";
import { getHealth } from "../../services/api";
import { useAuthSession } from "../../auth/AuthSession";

function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    shield:
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    dashboard:
      '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    verify:
      '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    cases:
      '<path d="M8 3H4a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1h-4"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/>',
    system:
      '<circle cx="12" cy="12" r="3"/><path d="M12 2v3"/><path d="M12 19v3"/><path d="M2 12h3"/><path d="M19 12h3"/><path d="m4.9 4.9 2.1 2.1"/><path d="m17 17 2.1 2.1"/><path d="m4.9 19.1 2.1-2.1"/><path d="m17 7 2.1-2.1"/>',
    doc:
      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
  };
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <g dangerouslySetInnerHTML={{ __html: paths[name] ?? paths.doc }} />
    </svg>
  );
}

const NAV = [
  { to: "/", label: "Dashboard", icon: "dashboard" },
  { to: "/verify", label: "Verify Certificate", icon: "verify" },
  { to: "/investigations", label: "Investigations", icon: "cases", section: true },
  { to: "/system", label: "System Status", icon: "system" },
];

export function AppShell({
  pageTitle,
  children,
}: {
  pageTitle: string;
  children: ReactNode;
}) {
  const { path } = useRouter();
  const { user } = useUser();
  const { signOut } = useAuthSession();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((h) => {
        if (active) setHealth(h);
      })
      .catch(() => {
        if (active) setHealth(null);
      });
    return () => {
      active = false;
    };
  }, []);

  const closeSidebar = () => setSidebarOpen(false);
  const isActive = (item: (typeof NAV)[number]) =>
    item.section
      ? path === item.to || path.startsWith(`${item.to}/`)
      : path === item.to;

  const healthOk = health?.status === "ok" && health.model_loaded;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      {sidebarOpen ? (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation menu"
          onClick={closeSidebar}
        />
      ) : null}

      <aside className={`sidebar${sidebarOpen ? " sidebar--open" : ""}`} aria-label="Primary">
        <div className="sidebar__brand">
          <span className="sidebar__logo" aria-hidden="true">
            <Icon name="shield" />
          </span>
          <span>
            <span className="sidebar__brand-name">CertiGuard AI</span>
            <span className="sidebar__brand-sub">Verification &amp; Forensics</span>
          </span>
        </div>

        <nav className="sidebar__nav">
          <span className="sidebar__group-label">Workspace</span>
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`sidebar__link${isActive(item) ? " sidebar__link--active" : ""}`}
              aria-current={isActive(item) ? "page" : undefined}
              onClick={closeSidebar}
            >
              <Icon name={item.icon} />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div>
            AI-based preliminary verification. Evidence is indicative and
            requires human review for high-stakes decisions.
          </div>
          <div className="sidebar__status">
            <span
              className={`status-dot ${
                healthOk
                  ? "status-dot--ok"
                  : health
                    ? "status-dot--warn"
                    : "status-dot--unknown"
              }`}
              aria-hidden="true"
            />
            <span>
              {healthOk
                ? `Backend online · ${health.model_version ?? "model"}`
                : health
                  ? "Backend degraded"
                  : "Backend unreachable"}
            </span>
          </div>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="sidebar-open-btn"
            aria-label="Open navigation menu"
            onClick={() => setSidebarOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div className="topbar__left">
            <span className="topbar__title">{pageTitle}</span>
          </div>
          <div className="topbar__spacer" />
          <div className="topbar__meta">
            <span className="topbar__chip topbar__chip--status">
              <span
                className={`status-dot ${
                  healthOk ? "status-dot--ok" : health ? "status-dot--warn" : "status-dot--error"
                }`}
                aria-hidden="true"
              />
              <span className="topbar__chip-text">
                {healthOk ? "Systems operational" : "Backend unavailable"}
              </span>
            </span>
            {health?.model_version ? (
              <span className="topbar__chip topbar__chip--model mono">
                model: {health.model_version}
              </span>
            ) : null}
            <div className="topbar__user">
              <span className="topbar__user-avatar" aria-hidden="true">
                {(user?.firstName ?? user?.username ?? "U").slice(0, 1).toUpperCase()}
              </span>
              <span className="topbar__user-name">
                {(user?.firstName ?? "User") +
                  (user?.primaryEmailAddress?.emailAddress
                    ? ` · ${user.primaryEmailAddress.emailAddress}`
                    : "")}
              </span>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => signOut()}
              >
                Sign out
              </button>
            </div>
          </div>
        </header>

        <main className="app-content" id="main-content">
          <div className="page">{children}</div>
        </main>

        <footer className="app-footer">
          <span>CertiGuard AI — AI Certificate Verification &amp; Digital Forensics Platform</span>
          <span>Preliminary assessment · not a legal authentication verdict</span>
        </footer>
      </div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-header__title">{title}</h1>
        {subtitle ? <p className="page-header__subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-header__actions">{actions}</div> : null}
    </div>
  );
}