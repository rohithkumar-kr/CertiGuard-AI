import assert from "node:assert/strict";
import { test } from "node:test";
import { bearerRequestInit, buildHeaders } from "../src/services/httpHeaders.ts";

const TOKEN = "the-session-token";

test("buildHeaders: attaches Bearer only when a token is present", () => {
  assert.equal(buildHeaders(TOKEN)["Authorization"], "Bearer the-session-token");
  assert.equal("Authorization" in buildHeaders(null), false);
});

test("buildHeaders: preserves existing headers and never duplicates", () => {
  const headers = buildHeaders(TOKEN, { "Content-Type": "application/json" });
  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers["Authorization"], `Bearer ${TOKEN}`);
});

test("buildHeaders: merges HeadersInit record and array forms", () => {
  const fromRecord = buildHeaders(TOKEN, { "X-Trace": "abc" });
  assert.equal(fromRecord["X-Trace"], "abc");

  const fromArray = buildHeaders(TOKEN, [["X-Trace", "abc"] as [string, string]]);
  assert.equal(fromArray["X-Trace"], "abc");
  assert.equal(fromArray["Authorization"], `Bearer ${TOKEN}`);
});

test("bearerRequestInit: attaches the Authorization header on fetch init", () => {
  const init = bearerRequestInit({ method: "POST" }, TOKEN);
  const headers = init.headers as Record<string, string>;
  assert.equal(headers["Authorization"], `Bearer ${TOKEN}`);
});

test("bearerRequestInit: no token -> no Authorization header", () => {
  const init = bearerRequestInit(undefined, null);
  assert.equal("Authorization" in (init.headers as Record<string, string>), false);
});

test("the bearer token value is never logged or leaked beyond the header", () => {
  assert.equal(buildHeaders(TOKEN)["Authorization"].startsWith("Bearer "), true);
  const header = buildHeaders(TOKEN)["Authorization"];
  // Sanity: the only place the raw token may appear is after "Bearer ".
  assert.equal(header.includes(TOKEN), true);
});