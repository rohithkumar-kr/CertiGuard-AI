import { ClerkProvider } from "@clerk/clerk-react";
import type { ReactNode } from "react";

const CLERK_PUBLISHABLE_KEY = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY ?? "").trim();

function MisconfiguredScreen() {
  return (
    <div className="auth-screen">
      <div className="auth-screen__card">
        <div className="auth-brand">
          <span className="auth-brand__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </span>
          <span className="auth-brand__name">CertiGuard AI</span>
          <span className="auth-brand__sub">Authentication is not configured</span>
        </div>
        <div className="auth-screen__notice">
          Set <code className="mono">VITE_CLERK_PUBLISHABLE_KEY</code> in{" "}
          <code className="mono">frontend/.env</code> (copy from{" "}
          <code className="mono">frontend/.env.example</code>) to enable sign in.
        </div>
      </div>
    </div>
  );
}

export function LoadingScreen({ notice }: { notice?: string | null }) {
  return (
    <div className="auth-screen">
      <div className="auth-screen__card auth-screen__card--centered">
        <div className="auth-brand">
          <span className="auth-brand__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </span>
          <span className="auth-brand__name">CertiGuard AI</span>
          <span className="auth-brand__sub">Establishing a secure session…</span>
        </div>
        {notice ? (
          <div className="auth-screen__notice" role="status">
            <span className="spinner spinner--sm" aria-hidden="true" />
            <span>{notice}</span>
          </div>
        ) : (
          <div className="auth-screen__notice muted" role="status">
            <span className="spinner spinner--sm" aria-hidden="true" />
            Preparing your workspace…
          </div>
        )}
      </div>
    </div>
  );
}

export function ClerkRoot({ children }: { children: ReactNode }) {
  if (!CLERK_PUBLISHABLE_KEY) {
    return <MisconfiguredScreen />;
  }
  return (
    <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY}>{children}</ClerkProvider>
  );
}