import { useAuth, useClerk } from "@clerk/clerk-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { computeAuthStatus, type AuthSessionStatus } from "../services/authFlow";
import {
  resetSessionExpiredGuard,
  setAuthToken,
  setAuthTokenRefreshHandler,
  setSessionExpiredHandler,
} from "../services/authToken";

interface AuthSessionContextValue {
  /** "loading" while Clerk is loading or the session token is being minted. */
  status: AuthSessionStatus;
  /** Current in-memory session token (null until Ready). */
  token: string | null;
  /** Transient notice to show on the auth screen (e.g. session expired). */
  notice: string | null;
  clearNotice: () => void;
  signOut: () => void;
}

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

const TOKEN_MINT_RETRIES = 3;
/** Cadence while the first token is still being minted (session pending). */
const INITIAL_RETRY_MS = 1500;
/** Keep-alive cadence for an established (ready) session. */
const TOKEN_REFRESH_MS = 60_000;
const RETRY_DELAY_MS = [200, 400, 600];
/** After this many initial mint failures, tell the user we are still waiting. */
const STALL_NOTICE_AFTER = 12;

export function AuthSessionProvider({ children }: { children: ReactNode }) {
  // Do not treat a pending session as signed out: while Clerk says the session
  // exists (even if not yet fully active), the gate must keep showing "loading"
  // instead of dropping the user back to the sign-in screen.
  const { isLoaded, isSignedIn, getToken } = useAuth({ treatPendingAsSignedOut: false });
  const { signOut: clerkSignOut } = useClerk();

  const [token, setToken] = useState<string | null>(null);
  const [tokenReady, setTokenReady] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const tokenReadyRef = useRef(false);
  const isSignedInRef = useRef(false);
  const mintFailuresRef = useRef(0);

  useEffect(() => {
    isSignedInRef.current = isSignedIn === true;
  }, [isSignedIn]);

  const setReadyRef = (ready: boolean) => {
    tokenReadyRef.current = ready;
    setTokenReady(ready);
  };

  const resetSessionState = useCallback(() => {
    mintFailuresRef.current = 0;
    setReadyRef(false);
    setToken(null);
    setAuthToken(null);
    resetSessionExpiredGuard();
  }, []);

  /** Mint a fresh Clerk session token with a small retry around transient
   * failures. Returns null only when Clerk is genuinely unable to issue one. */
  const mintToken = useCallback(async (): Promise<string | null> => {
    for (let attempt = 0; attempt < TOKEN_MINT_RETRIES; attempt++) {
      try {
        const t = await getToken();
        if (t) return t;
      } catch {
        // fall through to retry
      }
      await new Promise((r) => setTimeout(r, RETRY_DELAY_MS[attempt] ?? 500));
    }
    return null;
  }, [getToken]);

  const applyToken = useCallback((t: string) => {
    mintFailuresRef.current = 0;
    setAuthToken(t);
    setToken(t);
    setReadyRef(true);
    resetSessionExpiredGuard();
    setNotice(null);
  }, []);

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      resetSessionState();
      setNotice(null);
      return;
    }

    let active = true;
    let timer: number | undefined;

    const attempt = async () => {
      const t = await mintToken();
      if (!active) return;

      if (t) {
        applyToken(t);
        return;
      }

      // Signed in but the token cannot be minted yet (e.g. the session is
      // still pending after sign-up or a transient token-issuance failure).
      // NEVER sign the user out here: signing out on a mere mint failure is
      // what previously bounced users back to the sign-in screen. Keep the
      // loading gate and let Clerk's own state decide when the session is
      // truly gone (isSignedIn false -> auth screen).
      mintFailuresRef.current += 1;
      if (mintFailuresRef.current === STALL_NOTICE_AFTER) {
        setNotice(
          "We are still establishing your secure session. If this keeps loading, please sign out and sign in again.",
        );
      }
    };

    const scheduleNext = () => {
      const delay = tokenReadyRef.current ? TOKEN_REFRESH_MS : INITIAL_RETRY_MS;
      timer = window.setTimeout(() => {
        void attempt().finally(scheduleNext);
      }, delay);
    };

    void attempt().finally(scheduleNext);

    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [isLoaded, isSignedIn, mintToken, applyToken, resetSessionState]);

  // The API layer asks for a genuinely fresh (uncached) token before ever
  // interpreting a 401 as session expiration. Only Clerk can decide whether a
  // session can still issue tokens.
  useEffect(() => {
    setAuthTokenRefreshHandler(async () => {
      if (!isSignedInRef.current) return null;
      try {
        const t = await getToken({ skipCache: true });
        if (t) setAuthToken(t);
        return t ?? null;
      } catch {
        return null;
      }
    });
    return () => setAuthTokenRefreshHandler(null);
  }, [getToken]);

  const handleSessionExpired = useCallback(() => {
    // Reached only when the backend rejected an authenticated request AND
    // Clerk could not mint a replacement token (or rejected the fresh one too).
    setNotice("Your session has ended. Please sign in again to continue.");
    resetSessionState();
    void clerkSignOut();
  }, [clerkSignOut, resetSessionState]);

  useEffect(() => {
    setSessionExpiredHandler(handleSessionExpired);
    return () => setSessionExpiredHandler(null);
  }, [handleSessionExpired]);

  const clearNotice = useCallback(() => setNotice(null), []);

  const signOut = useCallback(() => {
    setNotice(null);
    resetSessionState();
    // The refresh handler must not mint after an explicit sign-out.
    void clerkSignOut();
  }, [clerkSignOut, resetSessionState]);

  const status: AuthSessionStatus = useMemo(
    () =>
      computeAuthStatus({
        isLoaded: isLoaded === true,
        isSignedIn: isSignedIn === true,
        tokenReady,
      }),
    [isLoaded, isSignedIn, tokenReady],
  );

  const value = useMemo<AuthSessionContextValue>(
    () => ({ status, token, notice, clearNotice, signOut }),
    [status, token, notice, clearNotice, signOut],
  );

  return (
    <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>
  );
}

export function useAuthSession(): AuthSessionContextValue {
  const ctx = useContext(AuthSessionContext);
  if (!ctx) {
    throw new Error("useAuthSession must be used within AuthSessionProvider");
  }
  return ctx;
}