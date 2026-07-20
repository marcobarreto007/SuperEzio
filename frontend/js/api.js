/* SuperEzio — API Layer */
(function () {
  const API = location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

  // ── Authenticated fetch wrapper ──
  async function fetchWithAuth(path, opts = {}) {
    var DBG = "[fetchWithAuth]";
    var auth = window.SZ && window.SZ.auth;

    // ── Step 1: get token (prefer getValidToken if available) ──
    var token = null;
    if (auth && typeof auth.getValidToken === "function") {
      token = auth.getValidToken();
    } else if (auth && typeof auth.getToken === "function") {
      token = auth.getToken();
    }

    // Fallback: read localStorage directly (defensive)
    if (!token && auth && auth.isAuthenticated && auth.isAuthenticated()) {
      try { token = localStorage.getItem("sz_access_token"); } catch (_) { /* ignore */ }
      if (token) console.log(DBG, path, "fallback localStorage OK");
    }

    // Dev-mode helper: isAuthenticated is false but dev mode was detected earlier
    if (!token && auth && auth.getToken) {
      try { token = localStorage.getItem("sz_access_token"); } catch (_) { /* ignore */ }
    }

    // ── Step 2: if token missing or expired, try refresh before first request ──
    var needsRefresh = !token;
    if (token && auth && typeof auth.isAuthenticated === "function" && !auth.isAuthenticated()) {
      needsRefresh = true;
    }
    if (needsRefresh && auth && typeof auth.refreshToken === "function") {
      console.log(DBG, path, "token missing/expired, refreshing…");
      var newToken = await auth.refreshToken();
      if (newToken) {
        token = newToken;
        console.log(DBG, path, "refresh OK, token=" + newToken.substring(0, 12) + "…");
      } else {
        console.warn(DBG, path, "refresh returned null");
      }
    }

    // ── Step 3: build headers (Authorization always included when token exists) ──
    var headers = { ...(opts.headers || {}) };
    if (token) {
      headers["Authorization"] = "Bearer " + token;
      console.log(DBG, path, "Authorization: Bearer " + token.substring(0, 12) + "…");
    } else {
      console.warn(DBG, path, "NO TOKEN — request will NOT have Authorization header");
    }
    if (!headers["Accept"]) {
      headers["Accept"] = "application/json";
    }
    opts = { ...opts, headers };

    // ── Step 4: execute ──
    var r = await fetch(API + path, opts);
    console.log(DBG, path, "status=" + r.status);

    // ── Step 5: on 401, try refresh once ──
    if (r.status === 401 && auth && typeof auth.refreshToken === "function") {
      console.log(DBG, path, "401, attempting refresh retry…");
      var newToken2 = await auth.refreshToken();
      if (newToken2) {
        headers["Authorization"] = "Bearer " + newToken2;
        r = await fetch(API + path, { ...opts, headers });
        console.log(DBG, path, "retry status=" + r.status);
      } else {
        console.warn(DBG, path, "refresh failed after 401, showing login modal");
        if (typeof auth.clearTokens === "function") auth.clearTokens();
        if (typeof auth.showLogin === "function") auth.showLogin();
      }
    }

    console.log(DBG, path, "final status=" + r.status);
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
    fetchMangalaSummary() { return fetchJson("/cockpit/mangala"); },
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
