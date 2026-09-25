import assert from "node:assert/strict";
import { test } from "node:test";
import {
  classifyApiFailure,
  computeAuthStatus,
  recoverFromAuthenticated401,
} from "../src/services/authFlow.ts";

test("computeAuthStatus: Clerk not loaded is loading, never signed-out", () => {
  assert.equal(computeAuthStatus({ isLoaded: false, isSignedIn: false, tokenReady: false }), "loading");
  assert.equal(computeAuthStatus({ isLoaded: false, isSignedIn: true, tokenReady: false }), "loading");
});

test("computeAuthStatus: loaded + signed out -> signed-out (auth screen)", () => {
  assert.equal(computeAuthStatus({ isLoaded: true, isSignedIn: false, tokenReady: false }), "signed-out");
});

test("computeAuthStatus: signed in but token not minted stays loading (pending session)", () => {
  assert.equal(computeAuthStatus({ isLoaded: true, isSignedIn: true, tokenReady: false }), "loading");
});

test("computeAuthStatus: signed in + token ready -> ready (protected app may mount)", () => {
  assert.equal(computeAuthStatus({ isLoaded: true, isSignedIn: true, tokenReady: true }), "ready");
});

test("classifyApiFailure: 401 on an authenticated request is session-expired", () => {
  assert.equal(classifyApiFailure(401, true), "session-expired");
});

test("classifyApiFailure: anonymous 401 is NOT session-expired", () => {
  assert.equal(classifyApiFailure(401, false), "other");
});

test("classifyApiFailure: 403/404/5xx never sign the user out", () => {
  for (const status of [403, 404, 422, 500, 503]) {
    assert.equal(classifyApiFailure(status, true), "other", `status ${status}`);
    assert.equal(classifyApiFailure(status, false), "other", `status ${status}`);
  }
});

test("recoverFromAuthenticated401: fresh token -> recoverable", async () => {
  const attempt = await recoverFromAuthenticated401(async () => "fresh-token");
  assert.equal(attempt.recoverable, true);
  assert.equal(attempt.freshToken, "fresh-token");
});

test("recoverFromAuthenticated401: no token from Clerk -> not recoverable (genuine expiry)", async () => {
  const attempt = await recoverFromAuthenticated401(async () => null);
  assert.equal(attempt.recoverable, false);
  assert.equal(attempt.freshToken, null);
});

test("recoverFromAuthenticated401: Clerk throwing -> not recoverable", async () => {
  const attempt = await recoverFromAuthenticated401(async () => {
    throw new Error("session not active");
  });
  assert.equal(attempt.recoverable, false);
  assert.equal(attempt.freshToken, null);
});

test("recoverFromAuthenticated401: rejection must not crash the caller", async () => {
  const attempt = await recoverFromAuthenticated401(async () => Promise.reject(new Error("boom")));
  assert.equal(attempt.recoverable, false);
});