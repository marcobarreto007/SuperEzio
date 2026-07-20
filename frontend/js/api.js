/* SuperEzio — API Layer */
(function () {
  const API = location.protocol === "file:" ? "http://127.0.0.1:8002" : "";

  // ── Authenticated fetch wrapper ──
  async function fetchWithAuth(path, opts = {}) {
    var DBG = "[fetchWithAuth]";
    var auth = window.SZ && window.SZ.auth;

    // ── Step 1: get token ──
    //   Tries, in order: getValidToken() -> getToken() -> localStorage direct
    var token = null;
    if (auth) {
      if (typeof auth.getValidToken === "function") {
        token = auth.getValidToken();
      }
      if (!token && typeof auth.getToken === "function") {
        token = auth.getToken();
      }
    }
    // Defensive: read localStorage directly if both methods failed
    if (!token) {
      try {
        var raw = localStorage.getItem("sz_access_token");
        if (raw) { token = raw; console.log(DBG, "path=" + path + " fallback localStorage OK"); }
      } catch (_) { /* ignore */ }
    }

    // ── Step 2: if token missing or expired, try refresh before first request ──
    if (!token && auth && typeof auth.refreshToken === "function") {
      console.log(DBG, "path=" + path + " token missing, attempting refresh…");
      var newToken = await auth.refreshToken();
      if (newToken) {
        token = newToken;
        console.log(DBG, "path=" + path + " refresh OK token=" + newToken.substring(0, 12) + "…");
      }
    } else if (token && auth && typeof auth.isAuthenticated === "function" && !auth.isAuthenticated()) {
      // Token exists but expired — try refresh
      console.log(DBG, "path=" + path + " token expired, attempting refresh…");
      var refreshed = await auth.refreshToken();
      if (refreshed) {
        token = refreshed;
        console.log(DBG, "path=" + path + " refresh OK token=" + refreshed.substring(0, 12) + "…");
      } else {
        console.warn(DBG, "path=" + path + " refresh returned null — using expired token (will likely get 401)");
      }
    }

    // ── Step 3: build headers (Authorization ALWAYS included when token exists) ──
    var headers = { ...(opts.headers || {}) };
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    } else {
      console.warn(DBG, "path=" + path + " NO TOKEN — request will NOT have Authorization header");
    }
    if (!headers["Accept"]) {
      headers["Accept"] = "application/json";
    }
    opts = { ...opts, headers };

    // ── Step 4: execute ──
    var r = await fetch(API + path, opts);
    var preview = token ? token.substring(0, 12) + "…" : "none";
    console.log(DBG, "path=" + path + " token=" + preview + " status=" + r.status);

    // ── Step 5: on 401, try refresh + retry once ──
    if (r.status === 401 && auth && typeof auth.refreshToken === "function") {
      console.log(DBG, "path=" + path + " status=401 attempting refresh retry…");
      var retryToken = await auth.refreshToken();
      if (retryToken) {
        headers["Authorization"] = "Bearer " + retryToken;
        r = await fetch(API + path, { ...opts, headers });
        var retryPreview = retryToken.substring(0, 12) + "…";
        console.log(DBG, "path=" + path + " token=" + retryPreview + " retry_status=" + r.status);
      } else {
        console.warn(DBG, "path=" + path + " refresh failed after 401, showing login modal");
        if (typeof auth.clearTokens === "function") auth.clearTokens();
        if (typeof auth.showLogin === "function") auth.showLogin();
      }
    }

    console.log(DBG, "path=" + path + " final status=" + r.status);
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
    fetchMangalaOpportunities() { return fetchJson("/cockpit/mangala/opportunities"); },
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
