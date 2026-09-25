import { ClerkRoot, LoadingScreen } from "./auth/AuthProvider";
import { AuthSessionProvider, useAuthSession } from "./auth/AuthSession";
import { AuthScreen } from "./auth/AuthScreen";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { Router, useRouter } from "./router/Router";
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

function RedirectingNotice() {
  return (
    <div className="card">
      <div className="state" role="status">
        <div className="state__icon">
          <span className="spinner" aria-hidden="true" />
        </div>
        <div>
          <p className="state__title">Redirecting you securely…</p>
          <p className="state__message">
            CertiGuard AI is completing the authentication flow.
          </p>
        </div>
      </div>
    </div>
  );
}

function RouterFallback() {
  const { path } = useRouter();
  // While an authentication flow completes, the hash briefly holds Clerk
  // internal paths (sign-in/sign-up sub-routes, OAuth callbacks). Those are
  // transient, not broken links — show a subtle notice instead of "not found".
  const transient =
    path === "/sign-in" ||
    path === "/sign-up" ||
    path.startsWith("/sign-in/") ||
    path.startsWith("/sign-up/") ||
    path.startsWith("/oauth") ||
    path.startsWith("/sso");

  if (transient) {
    return <RedirectingNotice />;
  }
  return (
    <AppShell pageTitle="Not found">
      <NotFound />
    </AppShell>
  );
}

function ProtectedApp() {
  return (
    <Router
      fallback={<RouterFallback />}
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

/**
 * AuthGate — the single rendering decision point.
 *
 * Status is owned by AuthSessionProvider, which only reports "ready" once a
 * fresh Clerk session token has actually been minted and handed to the api
 * client. This closes the flicker bug: until then the protected app is not
 * mounted at all, so no request can fire without a token and no 401 can
 * bounce the app back to the sign-in screen.
 */
function AuthGate() {
  const { status, notice, clearNotice } = useAuthSession();

  if (status === "loading") {
    return <LoadingScreen notice={notice} />;
  }

  if (status === "signed-out") {
    return <AuthScreen notice={notice} onDismiss={clearNotice} />;
  }

  return (
    <ErrorBoundary>
      <ProtectedApp />
    </ErrorBoundary>
  );
}

function App() {
  return (
    <ClerkRoot>
      <AuthSessionProvider>
        <AuthGate />
      </AuthSessionProvider>
    </ClerkRoot>
  );
}

export default App;