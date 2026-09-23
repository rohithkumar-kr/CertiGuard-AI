import { Router } from "./router/Router";
import { AppShell } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { VerifyPage } from "./pages/VerifyPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { SystemPage } from "./pages/SystemPage";

function NotFound() {
  return (
    <div className="card">
      <div className="state" role="status">
        <div className="state__icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" />
            <path d="M12 17h.01" />
          </svg>
        </div>
        <div>
          <p className="state__title">Page not found</p>
          <p className="state__message">
            The requested address does not exist. Use the navigation to return
            to a known area of the platform.
          </p>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <Router
      fallback={
        <AppShell pageTitle="Not found">
          <NotFound />
        </AppShell>
      }
      routes={[
        {
          path: "/",
          element: (
            <AppShell pageTitle="Dashboard">
              <DashboardPage />
            </AppShell>
          ),
        },
        {
          path: "/verify",
          element: (
            <AppShell pageTitle="Verify Certificate">
              <VerifyPage />
            </AppShell>
          ),
        },
        {
          path: "/investigations",
          element: (
            <AppShell pageTitle="Investigations">
              <InvestigationsPage />
            </AppShell>
          ),
        },
        {
          path: "/investigations/:id",
          element: (
            <AppShell pageTitle="Investigation">
              <InvestigationDetailPage />
            </AppShell>
          ),
        },
        {
          path: "/investigations/:id/:tab",
          element: (
            <AppShell pageTitle="Investigation">
              <InvestigationDetailPage />
            </AppShell>
          ),
        },
        {
          path: "/system",
          element: (
            <AppShell pageTitle="System Status">
              <SystemPage />
            </AppShell>
          ),
        },
      ]}
    />
  );
}

export default App;