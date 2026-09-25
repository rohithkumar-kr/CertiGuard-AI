/**
 * Pure authentication-lifecycle helpers.
 *
 * Kept free of React, Clerk, fetch and environment globals so the exact
 * decision rules can be unit-tested with the Node test runner (no extra
 * dependencies). The React layer (AuthSession, api) only wires these rules to
 * live sources of truth.
 */

export type AuthSessionStatus = "loading" | "signed-out" | "ready";

/**
 * The single source of truth for the application's authentication gate.
 *
 * - Clerk not loaded  -> still initializing, never signed out.
 * - Clerk loaded and signed out -> signed out (auth screen).
 * - Clerk signed in but the session token is not minted yet -> loading.
 *   A pending-but-signed-in session must NOT be shown the sign-in screen.
 * - Clerk signed in and token ready -> ready (protected app may mount).
 */
export function computeAuthStatus(args: {
  isLoaded: boolean;
  isSignedIn: boolean;
  tokenReady: boolean;
}): AuthSessionStatus {
  if (!args.isLoaded) return "loading";
  if (!args.isSignedIn) return "signed-out";
  return args.tokenReady ? "ready" : "loading";
}

export type ApiFailureKind = "ok" | "session-expired" | "other";

/**
 * Classify a backend response for the session-expiry decision.
 *
 * A 401 is only treated as session expiration when the request actually
 * carried a Bearer token. Anonymous 401s (token not minted yet), 403s, 404s
 * and 5xx responses are ordinary failures and must never sign the user out.
 */
export function classifyApiFailure(
  status: number,
  hadBearerToken: boolean,
): ApiFailureKind {
  return status === 401 && hadBearerToken ? "session-expired" : "other";
}

export interface FreshTokenAttempt {
  /** Genuinely fresh token from the session provider, or null. */
  freshToken: string | null;
  /** True when a fresh token was obtained (the 401 may be a stale-token race). */
  recoverable: boolean;
}

/**
 * On an authenticated 401, ask the session provider to mint a genuinely fresh
 * (uncached) token. If Clerk still issues one the session is alive and the
 * request should be retried once with the new token; otherwise the session is
 * genuinely over and the caller may sign the user out.
 */
export async function recoverFromAuthenticated401(
  refresh: () => Promise<string | null>,
): Promise<FreshTokenAttempt> {
  try {
    const fresh = await refresh();
    if (fresh) return { freshToken: fresh, recoverable: true };
    return { freshToken: null, recoverable: false };
  } catch {
    return { freshToken: null, recoverable: false };
  }
}