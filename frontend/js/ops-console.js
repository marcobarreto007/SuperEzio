/* SuperEzio — System Operations Console */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  function setStatusText(id, text, className) {
    const el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = className || "";
  }

  function normalizeBroker(details, portfolio) {
    const missionIbkr = details?.mission?.broker?.ibkr || {};
    if (portfolio && typeof portfolio === "object") {
      return {
        provider: portfolio.provider || missionIbkr.provider || "IBKR",
        connection: portfolio.connection || missionIbkr.connection || "unknown",
        mode: portfolio.mode || missionIbkr.mode || "unknown",
        paper_port: portfolio.paper === true,
        can_read_account: portfolio.connected === true,
        can_submit_orders: portfolio.can_submit_orders === true,
        account_equity: portfolio.equity ?? missionIbkr.account_equity,
        positions_count: portfolio.positions_count ?? missionIbkr.positions_count,
        orders_count: portfolio.orders_count ?? missionIbkr.orders_count,
        broker_orders_count: portfolio.broker_orders_count ?? missionIbkr.broker_orders_count,
        verification_source: "cockpit_portfolio_live",
      };
    }
    return missionIbkr;
  }

  function brokerDetailsForChip(details, ibkr) {
    const merged = details && typeof details === "object" ? JSON.parse(JSON.stringify(details)) : {};
    merged.mission = merged.mission || {};
    merged.mission.broker = merged.mission.broker || {};
    merged.mission.broker.ibkr = ibkr || {};
    return merged;
  }

  function renderBrokerDiagnostics(details, portfolio) {
    const ibkr = normalizeBroker(details, portfolio);
    const paperTrading = details?.mission?.paper_trading?.active === true;
    const connection = String(ibkr.connection || "");
    const modeRaw = String(ibkr.mode || "");
    const canRead = ibkr.can_read_account === true || connection.includes("connected");
    const paperTrade = paperTrading || ibkr.paper_port === true || modeRaw.toLowerCase().includes("paper");
    const canSubmit = ibkr.can_submit_orders === true && paperTrade;
    const liveBlocked = canRead && !paperTrade;

    const className = liveBlocked ? "ops-status-warn"
      : canSubmit ? "ops-status-ok"
      : paperTrade ? "ops-status-ok"
      : canRead ? "ops-status-ok"
      : "ops-status-err";

    const status = liveBlocked ? "LIVE BLOCKED"
      : canSubmit ? "PAPER ORDER ENABLED"
      : paperTrade ? "PAPER CONNECTED"
      : canRead ? "CONNECTED READ-ONLY"
      : "NOT CONNECTED";

    const mode = liveBlocked ? "live_blocked"
      : modeRaw || (paperTrade ? "paper_read_only" : "read_only_no_orders");

    const equity = ibkr.account_equity != null ? String(ibkr.account_equity) : "--";
    const positions = ibkr.positions_count != null ? String(ibkr.positions_count) : "--";

    setStatusText("ops-broker-provider", ibkr.provider || "IBKR", className);
    setStatusText("ops-broker-status", status, className);
    setStatusText("ops-broker-mode", mode, liveBlocked ? "ops-status-warn" : className);
    setStatusText("ops-broker-equity", equity, equity === "--" ? "ops-status-warn" : "ops-status-ok");
    setStatusText("ops-broker-positions", positions, "ops-status-ok");

    if (typeof SZ.updateBrokerStatus === "function") {
      SZ.updateBrokerStatus(brokerDetailsForChip(details, ibkr));
    }
  }

  async function loadDiagnostics() {
    let hd = null;
    let portfolio = null;

    // 1. Health Status
    try {
      if (typeof SZ.api.fetchHealthDetails === "function") {
        hd = await SZ.api.fetchHealthDetails();
        const statusEl = $("ops-health-status");
        if (statusEl) {
          statusEl.textContent = esc(hd.status || "UNKNOWN").toUpperCase();
          statusEl.className = hd.status === "ok" ? "ops-status-ok" : "ops-status-err";
        }

        const gpu = hd.checks?.gpu || {};
        const gpuEl = $("ops-health-gpu");
        if (gpuEl) {
          gpuEl.textContent = gpu.available ? `${esc(gpu.devices?.[0]?.name || "Yes")} (${gpu.devices?.[0]?.vram_mb || 0}MB)` : "No / CPU Only";
          gpuEl.className = gpu.available ? "ops-status-ok" : "ops-status-warn";
        }

        const redis = hd.checks?.redis || {};
        const redisEl = $("ops-health-redis");
        if (redisEl) {
          if (redis.status === "ok") {
            redisEl.textContent = `Connected (${esc(redis.url || "")})`;
            redisEl.className = "ops-status-ok";
          } else if (redis.status === "skipped") {
            redisEl.textContent = "Not required";
            redisEl.className = "ops-status-warn";
          } else {
            redisEl.textContent = `Unavailable (${esc(redis.status || "")})`;
            redisEl.className = "ops-status-err";
          }
        }

        const ceo = hd.checks?.local_models?.ceo || {};
        const orchestrator = hd.checks?.provider_local_orchestrator || hd.checks?.providers_summary?.primary || {};
        const ceoEl = $("ops-health-ceo");
        if (ceoEl) {
          if (ceo.reachable) {
            ceoEl.textContent = "Reachable (:8082)";
            ceoEl.className = "ops-status-ok";
          } else if (orchestrator.configured) {
            ceoEl.textContent = `Configured (${esc(orchestrator.model || "local orchestrator")})`;
            ceoEl.className = "ops-status-ok";
          } else {
            ceoEl.textContent = "Unavailable";
            ceoEl.className = "ops-status-err";
          }
        }
      }
    } catch (err) {
      console.warn("[SZ] Ops Console Health Details fetch failed:", err);
      const statusEl = $("ops-health-status");
      if (statusEl) {
        statusEl.textContent = "FETCH FAILED";
        statusEl.className = "ops-status-err";
      }
    }

    try {
      if (typeof SZ.api.fetchCockpitPortfolio === "function") {
        portfolio = await SZ.api.fetchCockpitPortfolio();
      }
    } catch (err) {
      console.warn("[SZ] Ops Console Cockpit Portfolio fetch failed:", err);
    }
    renderBrokerDiagnostics(hd, portfolio);

    // 2. Capabilities
    try {
      if (typeof SZ.api.fetchCapabilities === "function") {
        const cap = await SZ.api.fetchCapabilities();
        const listEl = $("ops-capabilities-list");
        if (listEl) {
          listEl.innerHTML = "";
          if (Array.isArray(cap.supported_tasks)) {
            cap.supported_tasks.forEach(task => {
              const li = document.createElement("li");
              li.textContent = esc(task);
              listEl.appendChild(li);
            });
          } else {
            listEl.innerHTML = "<li>No tasks found</li>";
          }
        }
      }
    } catch (err) {
      console.warn("[SZ] Ops Console Capabilities fetch failed:", err);
      const listEl = $("ops-capabilities-list");
      if (listEl) {
        listEl.innerHTML = "<li>Failed to fetch capabilities</li>";
      }
    }

    // 3. Performance Metrics
    try {
      if (typeof SZ.api.fetchMetrics === "function") {
        const metrics = await SZ.api.fetchMetrics();
        const latencyKeys = Object.keys(metrics).filter(k => k.endsWith("_latency"));
        const errorKeys = Object.keys(metrics).filter(k => k.endsWith("_error"));

        let totalLatency = 0;
        let latencyCount = 0;
        latencyKeys.forEach(k => {
          totalLatency += metrics[k] || 0;
          latencyCount++;
        });
        const avgLatency = latencyCount > 0 ? (totalLatency / latencyCount * 1000).toFixed(1) + " ms" : "No samples yet";

        let totalErrors = 0;
        errorKeys.forEach(k => {
          totalErrors += metrics[k] || 0;
        });

        const latEl = $("ops-metric-latency");
        if (latEl) latEl.textContent = avgLatency;

        const errEl = $("ops-metric-errors");
        if (errEl) {
          errEl.textContent = totalErrors;
          errEl.className = totalErrors > 0 ? "ops-status-err" : "ops-status-ok";
        }
      }
    } catch (err) {
      console.warn("[SZ] Ops Console Metrics fetch failed:", err);
      const latEl = $("ops-metric-latency");
      if (latEl) latEl.textContent = "--";
      const errEl = $("ops-metric-errors");
      if (errEl) errEl.textContent = "--";
    }

    // 4. Product Manifest
    try {
      if (typeof SZ.api.fetchManifest === "function") {
        const manifest = await SZ.api.fetchManifest();
        const descEl = $("ops-manifest-desc");
        if (descEl) descEl.textContent = esc(manifest.positioning || "No description");

        const principlesEl = $("ops-manifest-principles");
        if (principlesEl) {
          principlesEl.innerHTML = "";
          if (Array.isArray(manifest.operating_principles)) {
            manifest.operating_principles.forEach(p => {
              const li = document.createElement("li");
              li.textContent = esc(p);
              principlesEl.appendChild(li);
            });
          } else {
            principlesEl.innerHTML = "<li>No principles defined</li>";
          }
        }
      }
    } catch (err) {
      console.warn("[SZ] Ops Console Manifest fetch failed:", err);
      const principlesEl = $("ops-manifest-principles");
      if (principlesEl) {
        principlesEl.innerHTML = "<li>Failed to fetch manifest</li>";
      }
    }
  }

  function toggle(open) {
    const consoleEl = $("ops-console");
    if (!consoleEl) return;

    const action = () => {
      try {
        const isVisible = consoleEl.matches(":popover-open");
        const next = open ?? !isVisible;
        if (next) {
          consoleEl.showPopover();
          consoleEl.classList.add("open");
          // Auto-close SDCA Lab if open
          const sdca = document.getElementById("sdca-lab");
          if (sdca && sdca.matches(":popover-open")) {
            sdca.hidePopover();
            sdca.classList.remove("open");
          }
          loadDiagnostics();
        } else {
          consoleEl.hidePopover();
          consoleEl.classList.remove("open");
        }
      } catch (e) {
        // Fallback for older environments
        const next = open ?? !consoleEl.classList.contains("open");
        consoleEl.classList.toggle("open", next);
        if (next) {
          const sdca = $("sdca-lab");
          if (sdca) {
            sdca.classList.remove("open");
            sdca.setAttribute("aria-hidden", "true");
          }
          loadDiagnostics();
        }
      }
    };

    if (document.startViewTransition) {
      document.startViewTransition(action);
    } else {
      action();
    }
  }

  window.SZ = window.SZ || {};
  window.SZ.opsConsole = { toggle, loadDiagnostics };
})();
