import { SignIn, SignUp } from "@clerk/clerk-react";
import { useCallback, useEffect, useState } from "react";

/**
 * Clerk component styling bridged to the platform design tokens. The values
 * reference CSS custom properties defined in tokens.css (:root) so Clerk's UI
 * stays visually aligned with the rest of CertiGuard AI without hardcoding
 * colors in two places.
 */
const clerkAppearance = {
  variables: {
    colorPrimary: "var(--accent)",
    colorBackground: "var(--bg-surface)",
    colorForeground: "var(--text-primary)",
    colorInputBackground: "var(--bg-surface-2)",
    colorInputText: "var(--text-primary)",
    colorText: "var(--text-primary)",
    colorTextSecondary: "var(--text-secondary)",
    colorTextOnPrimaryBackground: "#ffffff",
    colorNeutral: "var(--text-muted)",
    colorBorder: "var(--border-strong)",
    colorDanger: "var(--red)",
    colorSuccess: "var(--green)",
    colorShimmer: "rgba(56, 189, 248, 0.35)",
    borderRadius: "6px",
    fontFamily: "var(--font-sans)",
    fontSize: "13px",
    fontWeight: {
      normal: 500,
      medium: 600,
      semibold: 650,
      bold: 700,
    },
  },
  elements: {
    rootBox: { width: "100%" },
    // The Clerk card is the form surface inside our card -- let it fill the
    // column and inherit the platform background/border.
    card: {
      width: "100%",
      boxShadow: "none",
      border: "none",
      background: "transparent",
    },
    header: { gap: "6px", padding: "0 0 6px" },
    headerTitle: {
      fontSize: "18px",
      fontWeight: 700,
      letterSpacing: "-0.02em",
      color: "var(--text-primary)",
    },
    headerSubtitle: {
      color: "var(--text-secondary)",
      fontSize: "12.5px",
    },
    formFieldLabel: {
      color: "var(--text-secondary)",
      fontSize: "12.5px",
      fontWeight: 600,
    },
    formFieldInput: {
      backgroundColor: "var(--bg-surface-2)",
      borderColor: "var(--border-strong)",
      color: "var(--text-primary)",
      fontSize: "13px",
    },
    formButtonPrimary: {
      background: "var(--primary)",
      color: "#ffffff",
      fontSize: "13px",
    },
    socialButtonsBlockButton: {
      backgroundColor: "var(--bg-surface-2)",
      borderColor: "var(--border-strong)",
      color: "var(--text-primary)",
    },
    dividerLine: { backgroundColor: "var(--border)" },
    dividerText: { color: "var(--text-faint)" },
    footerActionText: { color: "var(--text-faint)" },
    footerActionLink: { color: "var(--accent)" },
    formResendCodeLink: { color: "var(--accent)" },
    identityPreview: { backgroundColor: "var(--bg-surface-2)", border: "1px solid var(--border)" },
    identityPreviewEditButton: { color: "var(--accent)" },
    otpCodeFieldInput: {
      backgroundColor: "var(--bg-surface-2)",
      borderColor: "var(--border-strong)",
      color: "var(--text-primary)",
    },
    formFieldErrorText: { color: "var(--red)" },
    formFieldHintText: { color: "var(--text-muted)" },
    alert: {
      backgroundColor: "var(--red-soft)",
      borderColor: "rgba(248, 113, 113, 0.35)",
      color: "var(--text-primary)",
    },
    alertText: { color: "var(--text-primary)" },
    footer: { padding: "8px 0 0" },
  },
};

function ShieldIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

type AuthMode = "sign-in" | "sign-up";

const MODE_POINTS: Array<{ icon: string; title: string; body: string }> = [
  {
    icon: "M12 2 3 7v5c0 5 3.8 9 9 11 5.2-2 9-6 9-11V7z",
    title: "31-feature ML classifier",
    body: "Every certificate is scored against a fixed forensic feature set for preliminary fraud-risk assessment.",
  },
  {
    icon: "M5 3h14v7a7 7 0 0 1-14 0zM12 17v4M8 21h8",
    title: "Independent evidence fusion",
    body: "Issuer, tampering, structural and source checks merge into a single transparent decision.",
  },
  {
    icon: "M12 3 4 7v6c0 5 3.4 8 8 8s8-3 8-8V7zM9 12l2 2 4-4",
    title: "Private, per-user records",
    body: "Investigations are scoped to your account. Nothing is shared between users.",
  },
  {
    icon: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    title: "Secure Clerk sessions",
    body: "Authentication is handled by Clerk; your session token lives only in memory.",
  },
];

function useAuthMode(): [AuthMode, (mode: AuthMode) => void] {
  const [mode, setMode] = useState<AuthMode>(() => {
    const h = window.location.hash.replace(/^#/, "");
    if (h.startsWith("/sign-up")) return "sign-up";
    return "sign-in";
  });

  useEffect(() => {
    const sync = () => {
      const h = window.location.hash.replace(/^#/, "");
      // Clerk keeps its own sub-routes inside the hash (e.g.
      // "#/sign-in#forgot-password", "#/sign-up#verify-email-address");
      // matching by prefix keeps the active tab correct throughout a flow.
      if (h.startsWith("/sign-up")) setMode("sign-up");
      else if (h.startsWith("/sign-in")) setMode("sign-in");
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  const navigateMode = useCallback((next: AuthMode) => {
    if (next === "sign-up") window.location.hash = "/sign-up";
    else window.location.hash = "/sign-in";
  }, []);

  return [mode, navigateMode];
}

export function AuthScreen({
  notice,
  onDismiss,
}: {
  notice?: string | null;
  onDismiss?: () => void;
}) {
  const [mode, navigateMode] = useAuthMode();

  return (
    <div className="auth-screen auth-screen--split">
      <section className="auth-screen__panel" aria-label="About CertiGuard AI">
        <div className="auth-brand">
          <span className="auth-brand__icon" aria-hidden="true">
            <ShieldIcon />
          </span>
          <span className="auth-brand__name">CertiGuard AI</span>
          <span className="auth-brand__sub">
            AI Certificate Verification &amp; Digital Forensics
          </span>
        </div>

        <div className="auth-panel__copy">
          <h1 className="auth-panel__title">
            Preliminary fraud-risk intelligence for certificates
          </h1>
          <p className="auth-panel__lead">
            CertiGuard AI runs each document through an independent ML classifier,
            fusion engine and forensic checks — then shows you why, not just whether.
          </p>

          <ul className="auth-points">
            {MODE_POINTS.map((p) => (
              <li className="auth-points__item" key={p.title}>
                <span className="auth-points__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d={p.icon} />
                  </svg>
                </span>
                <span>
                  <span className="auth-points__title">{p.title}</span>
                  <span className="auth-points__body">{p.body}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <p className="auth-panel__note">
          Preliminary assessment only · not a legal authentication verdict.
        </p>
      </section>

      <section className="auth-screen__form" aria-label="Authentication">
        <div className="auth-screen__card">
          <div className="auth-screen__card-mobile-brand">
            <span className="auth-brand__icon" aria-hidden="true">
              <ShieldIcon />
            </span>
            <span className="auth-brand__name">CertiGuard AI</span>
          </div>

          {notice ? (
            <div className="auth-screen__notice" role="alert">
              <span>{notice}</span>
              {onDismiss ? (
                <button
                  type="button"
                  className="auth-screen__notice-dismiss"
                  aria-label="Dismiss"
                  onClick={onDismiss}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              ) : null}
            </div>
          ) : null}

          <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "sign-in"}
              className={`auth-tabs__tab${mode === "sign-in" ? " auth-tabs__tab--active" : ""}`}
              onClick={() => navigateMode("sign-in")}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "sign-up"}
              className={`auth-tabs__tab${mode === "sign-up" ? " auth-tabs__tab--active" : ""}`}
              onClick={() => navigateMode("sign-up")}
            >
              Create account
            </button>
          </div>

          <div className="auth-screen__body">
            {mode === "sign-up" ? (
              <SignUp
                routing="hash"
                signInUrl="/sign-in"
                afterSignInUrl="/"
                afterSignUpUrl="/"
                appearance={clerkAppearance}
              />
            ) : (
              <SignIn
                routing="hash"
                signInUrl="/sign-in"
                signUpUrl="/sign-up"
                afterSignInUrl="/"
                afterSignUpUrl="/"
                appearance={clerkAppearance}
              />
            )}
          </div>

          <p className="auth-screen__footnote">
            Authentication is handled securely by Clerk. Google sign-in appears
            only when your workspace has it enabled.
          </p>
        </div>
      </section>
    </div>
  );
}