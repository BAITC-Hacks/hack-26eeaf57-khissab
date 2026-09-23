import test from "node:test";
import assert from "node:assert/strict";
import { loadEmployeeResources } from "../src/loadEmployee.js";

function pending() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("profile becomes usable while the model is still pending", async () => {
  const profile = pending(), model = pending(), updates = [];
  const loading = loadEmployeeResources({
    employeeId: "E0002", request: (path) => path.startsWith("/employees/") ? profile.promise : model.promise,
    onProfile: (value) => updates.push(["profile", value]),
    onRecommendations: (value) => updates.push(["recommendations", value]),
    onProfileError: assert.fail, onRecommendationError: assert.fail,
  });
  profile.resolve({ skills: { system: 2 } });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(updates, [["profile", { skills: { system: 2 } }]]);
  model.resolve({ recommendations: ["course"] });
  await loading;
  assert.equal(updates[1][0], "recommendations");
});

test("model failure preserves the profile and reports its own retryable error", async () => {
  const updates = [], model = pending();
  const loading = loadEmployeeResources({
    employeeId: "E0002", request: (path) => path.startsWith("/employees/") ? Promise.resolve("profile") : model.promise,
    onProfile: (value) => updates.push(value), onRecommendations: assert.fail,
    onProfileError: assert.fail, onRecommendationError: (error) => updates.push(error.message),
  });
  model.reject(new Error("Recommendation unavailable"));
  await loading;
  assert.deepEqual(updates, ["profile", "Recommendation unavailable"]);
});
