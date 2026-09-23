import test from "node:test";
import assert from "node:assert/strict";
import { createApiRequest } from "../src/api.js";

function unauthorized() {
  return new Response(JSON.stringify({ detail: "Sign in to continue" }), {
    status: 401, headers: { "Content-Type": "application/json" },
  });
}

test("a delayed rejection from an old session preserves a newly opened demo session", async () => {
  let token = "expired-session";
  let finish;
  const request = createApiRequest("/api", {
    readToken: () => token,
    expireSession: () => { token = null; },
    fetchImpl: (_url, options) => {
      assert.equal(options.headers.Authorization, "Bearer expired-session");
      return new Promise((resolve) => { finish = resolve; });
    },
  });
  const oldRequest = request("/auth/me");
  token = "fresh-demo-session";
  finish(unauthorized());
  await assert.rejects(oldRequest, /Sign in to continue/);
  assert.equal(token, "fresh-demo-session");
});

test("an expired current session is cleared while its failed request reports the error", async () => {
  let token = "current-session";
  const request = createApiRequest("/api", {
    readToken: () => token,
    expireSession: () => { token = null; },
    fetchImpl: async () => unauthorized(),
  });
  await assert.rejects(request("/employees"), /Sign in to continue/);
  assert.equal(token, null);
});

test("incorrect sign-in credentials remain a form error without expiring another session", async () => {
  let token = "current-session";
  const request = createApiRequest("/api", {
    readToken: () => token,
    expireSession: () => { token = null; },
    fetchImpl: async () => unauthorized(),
  });
  await assert.rejects(request("/auth/login", { method: "POST" }), /Sign in to continue/);
  assert.equal(token, "current-session");
});
