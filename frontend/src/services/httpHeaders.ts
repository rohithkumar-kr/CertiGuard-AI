/**
 * Request-header construction for the API client.
 *
 * Isolated (no Vite globals, no fetch) so the Bearer-token behavior can be
 * unit-tested directly. The token is only ever added to requests handled by
 * the API module (all of which target the backend), never third-party origins.
 */

/** Build a plain header object from a HeadersInit, then attach the token. */
export function buildHeaders(
  authToken: string | null,
  init?: HeadersInit,
): Record<string, string> {
  const headers: Record<string, string> = {};
  if (init) {
    if (init instanceof Headers) {
      init.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(init)) {
      for (const [key, value] of init) headers[key] = value;
    } else {
      Object.assign(headers, init);
    }
  }
  if (authToken) headers["Authorization"] = `Bearer ${authToken}`;
  return headers;
}

/** Attach the Bearer token (when present) to a RequestInit while preserving it. */
export function bearerRequestInit(
  init: RequestInit | undefined,
  authToken: string | null,
): RequestInit {
  return init
    ? { ...init, headers: buildHeaders(authToken, init.headers) }
    : { headers: buildHeaders(authToken) };
}