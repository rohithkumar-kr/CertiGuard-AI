/**
 * Central holder for the Clerk session token used in the Authorization header.
 *
 * The token lives only in memory (never localStorage/sessionStorage) and is
 * minted/refreshed by the AuthSessionProvider. A single "session expired"
 * handler lets the UI react to a genuine backend 401 by resurfacing the
 * sign-in screen.
 */

let token: string | null = null;
let onSessionExpired: (() => void) | null = null;
let onTokenRefresh: (() => Promise<string | null>) | null = null;
let notified = false;

export function setAuthToken(value: string | null): void {
  token = value;
  // A freshly minted token represents a (new) live session, so re-arm the
  // single-fire guard — the next genuine 401 must be able to surface again.
  if (value) {
    notified = false;
  }
}

export function getAuthToken(): string | null {
  return token;
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

/**
 * Register the provider-owned token-minting callback. Called by the API layer
 * when a protected request returns 401: the app asks Clerk for a genuinely
 * fresh token (uncached) and only treats the 401 as session expiration when
 * no token can be issued. Never expose the returned token outside this module.
 */
export function setAuthTokenRefreshHandler(handler: (() => Promise<string | null>) | null): void {
  onTokenRefresh = handler;
}

/**
 * Ask the session provider to mint a fresh session token (source of truth:
 * Clerk). Returns null when Clerk is unable to issue one — the only case in
 * which an authenticated 401 may be treated as session expiration.
 */
export async function refreshSessionToken(): Promise<string | null> {
  if (!onTokenRefresh) return null;
  try {
    const fresh = await onTokenRefresh();
    return fresh || null;
  } catch {
    return null;
  }
}

export function resetSessionExpiredGuard(): void {
  notified = false;
}

/**
 * Notify the app that the backend rejected the attached token. Fire only once
 * per session: several in-flight requests can 401 together when a token
 * lapses, but we must sign the user out exactly once.
 */
export function triggerSessionExpired(): void {
  if (notified) return;
  notified = true;
  onSessionExpired?.();
}