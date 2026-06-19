/* SuperEzio — API Layer */
(function () {
  const API = location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

  async function fetchJson(path, opts = {}) {
    const r = await fetch(API + path, { headers: { Accept: "application/json" }, ...opts });
    if (!r.ok) throw new Error(`${path} ${r.status}`);
    return r.json();
  }

  window.SZ = window.SZ || {};
  window.SZ.api = {
    base: API,
    fetchJson,

    // Existing endpoints
    fetchHealth() { return fetchJson("/health"); },
    fetchChartData(ticker, tf = (window.SZ.config || {}).defaultTimeframe || "6M") {
      return fetchJson(`/api/chart-data/${encodeURIComponent(ticker)}?timeframe=${encodeURIComponent(tf)}`);
    },
    async submitTask(envelope) {
      const r = await fetch(API + "/task/submit", {
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
        const err = new Error(detail ? `/task/submit ${r.status}: ${detail}` : `/task/submit ${r.status}`);
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
      return fetchJson(`/task/cancel/${encodeURIComponent(runId)}`, { method: "POST" });
    },
    evaluateSDCA(body) {
      return fetch(API + "/api/sdca/evaluate", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(r => { if (!r.ok) throw new Error(`/api/sdca/evaluate ${r.status}`); return r.json(); });
    },
    sseURL(ticker, tf = "1D") {
      return `${API}/api/chart-sse/${encodeURIComponent(ticker)}?timeframe=${encodeURIComponent(tf)}&refresh_s=3&max_points=180`;
    },

    // NEW endpoints
    fetchHealthDetails() { return fetchJson("/health/details"); },
    fetchMetrics() { return fetchJson("/metrics"); },
    fetchManifest() { return fetchJson("/product/manifest"); },
    fetchCapabilities() { return fetchJson("/capabilities"); },
    fetchCockpitSummary() { return fetchJson("/cockpit/summary"); },
    fetchCockpitPortfolio() { return fetchJson("/cockpit/portfolio"); },
    fetchTrainingOrders() { return fetchJson("/training/orders"); },
    fetchTradeHistory(limit = 50) {
      return fetchJson(`/trades/history?limit=${encodeURIComponent(limit)}`);
    },
    fetchDecisionTrace(id) {
      return fetchJson(`/health/trace/${encodeURIComponent(id)}`);
    },
    fetchSentimentPulse() { return fetchJson("/sentiment/pulse"); },
    fetchSentimentAlerts(limit = 20) {
      return fetchJson(`/sentiment/alerts?limit=${encodeURIComponent(limit)}`);
    },
    predictNeural(body) {
      return fetch(API + "/experts/neural-decision/predict", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(r => { if (!r.ok) throw new Error(`/experts/neural-decision/predict ${r.status}`); return r.json(); });
    },
    neuralLogsURL() { return `${API}/neural/logs`; },
  };
})();
