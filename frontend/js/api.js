/* SuperEzio — API Layer */
(function () {
  const API = location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

  // ── Authenticated fetch wrapper ──
  async function fetchWithAuth(path, opts = {}) {
    const token = window.SZ?.auth?.getToken?.();
    const headers = { ...(opts.headers || {}) };
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    if (!headers["Accept"]) {
      headers["Accept"] = "application/json";
    }
    opts = { ...opts, headers };

    let r = await fetch(API + path, opts);

    // On 401, try refresh once
    if (r.status === 401 && window.SZ?.auth?.refreshToken) {
      const newToken = await window.SZ.auth.refreshToken();
      if (newToken) {
        headers["Authorization"] = "Bearer " + newToken;
        r = await fetch(API + path, { ...opts, headers });
      } else {
        window.SZ.auth.clearTokens?.();
        window.SZ.auth.showLogin?.();
      }
    }

    return r;
  }

  async function fetchJson(path, opts = {}) {
    const r = await fetchWithAuth(path, opts);
    if (!r.ok) throw new Error(path + " " + r.status);
    return r.json();
  }

  window.SZ = window.SZ || {};
  window.SZ.api = {
    base: API,
    fetchJson: fetchJson,
    fetchWithAuth: fetchWithAuth,

    // Existing endpoints
    fetchHealth() { return fetchJson("/health"); },
    fetchChartData(ticker, tf) {
      if (!tf) tf = (window.SZ.config || {}).defaultTimeframe || "6M";
      return fetchJson("/api/chart-data/" + encodeURIComponent(ticker) + "?timeframe=" + encodeURIComponent(tf));
    },
    async submitTask(envelope) {
      const r = await fetchWithAuth("/task/submit", {
        method: "POST",
        headers: { Accept: "application/x-ndjson", "Content-Type": "application/json" },
        body: JSON.stringify(envelope),
      });
      if (!r.ok) {
        let detail = "";
        let rawDetail = null;
        try {
          const data = await r.clone().json();
          rawDetail = data.detail || data.error || data;
          if (rawDetail && typeof rawDetail === "object") {
            detail = rawDetail.message || rawDetail.detail || JSON.stringify(rawDetail);
          } else {
            detail = rawDetail || "";
          }
        } catch (_) {
          try { detail = await r.text(); } catch (_) { detail = ""; }
        }
        const err = new Error(detail ? "/task/submit " + r.status + ": " + detail : "/task/submit " + r.status);
        err.status = r.status;
        if (rawDetail && typeof rawDetail === "object") {
          err.code = rawDetail.code || "";
          err.runId = rawDetail.run_id || "";
          err.sessionId = rawDetail.session_id || "";
          err.elapsed = rawDetail.elapsed || 0;
          err.detail = rawDetail;
        }
        throw err;
      }
      if (!r.body) throw new Error("/task/submit returned no stream body");
      return r;
    },
    fetchActiveTasks() { return fetchJson("/task/active"); },
    cancelTask(runId) {
      return fetchJson("/task/cancel/" + encodeURIComponent(runId), { method: "POST" });
    },
    evaluateSDCA(body) {
      return fetchWithAuth("/api/sdca/evaluate", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (r) { if (!r.ok) throw new Error("/api/sdca/evaluate " + r.status); return r.json(); });
    },
    sseURL(ticker, tf) {
      if (!tf) tf = "1D";
      return API + "/api/chart-sse/" + encodeURIComponent(ticker) + "?timeframe=" + encodeURIComponent(tf) + "&refresh_s=3&max_points=180";
    },

    // NEW endpoints
    fetchHealthDetails() { return fetchJson("/health/details"); },
    fetchMetrics() { return fetchJson("/metrics"); },
    fetchManifest() { return fetchJson("/product/manifest"); },
    fetchCapabilities() { return fetchJson("/capabilities"); },
    fetchCockpitSummary() { return fetchJson("/cockpit/summary"); },
    fetchCockpitPortfolio() { return fetchJson("/cockpit/portfolio"); },
    fetchTradeHistory(limit) {
      if (!limit) limit = 50;
      return fetchJson("/trades/history?limit=" + encodeURIComponent(limit));
    },
    fetchDecisionTrace(id) {
      return fetchJson("/health/trace/" + encodeURIComponent(id));
    },
    fetchSentimentPulse() { return fetchJson("/sentiment/pulse"); },
    fetchSentimentAlerts(limit) {
      if (!limit) limit = 20;
      return fetchJson("/sentiment/alerts?limit=" + encodeURIComponent(limit));
    },
    predictNeural(body) {
      return fetchWithAuth("/experts/neural-decision/predict", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (r) { if (!r.ok) throw new Error("/experts/neural-decision/predict " + r.status); return r.json(); });
    },
    neuralLogsURL() { return API + "/neural/logs"; },
  };
})();
