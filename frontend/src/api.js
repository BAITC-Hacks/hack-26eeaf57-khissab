function describeDetail(detail) {
  if (Array.isArray(detail)) return detail.map((item) => typeof item === "object" ? item.msg || JSON.stringify(item) : item).join("; ");
  if (detail && typeof detail === "object") {
    if (detail.message && detail.reasons) return `${detail.message}: ${detail.reasons.join(", ")}`;
    return JSON.stringify(detail);
  }
  return detail || "Request failed";
}

export function createApiRequest(baseUrl, {
  fetchImpl = globalThis.fetch,
  readToken = () => sessionStorage.getItem("career-quest-session"),
  expireSession = () => window.dispatchEvent(new Event("session-expired")),
} = {}) {
  return async function apiRequest(path, options = {}) {
    const token = readToken();
    const response = await fetchImpl(`${baseUrl}${path}`, {
      ...options,
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers },
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      // An old request must never sign out a session opened since it started.
      if (response.status === 401 && path !== "/auth/login" && token && token === readToken()) expireSession();
      throw new Error(describeDetail(payload.detail ?? payload));
    }
    return payload;
  };
}
