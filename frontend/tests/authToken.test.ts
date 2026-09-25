import assert from "node:assert/strict";
import { test } from "node:test";
import {
  getAuthToken,
  refreshSessionToken,
  resetSessionExpiredGuard,
  setAuthToken,
  setAuthTokenRefreshHandler,
  setSessionExpiredHandler,
  triggerSessionExpired,
} from "../src/services/authToken.ts";

test("token store: set/get round-trip", () => {
  setAuthToken("tok-1");
  assert.equal(getAuthToken(), "tok-1");
  setAuthToken(null);
  assert.equal(getAuthToken(), null);
});

test("token store: setting a token re-arms the single-fire expiry guard", () => {
  resetSessionExpiredGuard();
  setAuthToken("tok-rearm");
  let calls = 0;
  setSessionExpiredHandler(() => {
    calls += 1;
  });

  triggerSessionExpired();
  triggerSessionExpired(); // several in-flight 401s in the same session
  triggerSessionExpired();
  assert.equal(calls, 1, "handler must fire exactly once per session");

  // A freshly minted token represents a new session -> guard re-armed.
  setAuthToken("tok-next");
  triggerSessionExpired();
  assert.equal(calls, 2);
});

test("token store: unset handler is a no-op and does not throw", () => {
  setSessionExpiredHandler(null);
  triggerSessionExpired();
  resetSessionExpiredGuard();
});

test("refresh handler: delegates to the provider; returns null when unset", async () => {
  const fresh = await refreshSessionToken();
  assert.equal(fresh, null);

  let calls = 0;
  setAuthTokenRefreshHandler(async () => {
    calls += 1;
    return "fresh-from-clerk";
  });
  assert.equal(await refreshSessionToken(), "fresh-from-clerk");
  assert.equal(await refreshSessionToken(), "fresh-from-clerk");
  assert.equal(calls, 2);

  setAuthTokenRefreshHandler(null);
  assert.equal(await refreshSessionToken(), null);
});

test("refresh handler: a throwing provider resolves to null (never throws)", async () => {
  setAuthTokenRefreshHandler(async () => {
    throw new Error("session not active yet");
  });
  assert.equal(await refreshSessionToken(), null);
  setAuthTokenRefreshHandler(null);
});