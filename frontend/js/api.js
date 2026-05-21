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
    fetchChartData(ticker, tf = "6M") {
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
        try {
          const data = await r.clone().json();
          detail = data.detail || data.error || JSON.stringify(data);
        } catch (_) {
          try { detail = await r.text(); } catch (_) { detail = ""; }
        }
        throw new Error(detail ? `/task/submit ${r.status}: ${detail}` : `/task/submit ${r.status}`);
      }
      if (!r.body) throw new Error("/task/submit returned no stream body");
      return r;
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
