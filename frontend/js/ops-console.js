/* SuperEzio — System Operations Console */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  async function loadDiagnostics() {
    // 1. Health Status
    try {
      if (typeof SZ.api.fetchHealthDetails === "function") {
        const hd = await SZ.api.fetchHealthDetails();
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
          redisEl.textContent = redis.status === "ok" ? `Connected (${esc(redis.url || "")})` : `Offline (${esc(redis.status || "")})`;
          redisEl.className = redis.status === "ok" ? "ops-status-ok" : "ops-status-err";
        }

        const ceo = hd.checks?.local_models?.ceo || {};
        const ceoEl = $("ops-health-ceo");
        if (ceoEl) {
          ceoEl.textContent = ceo.reachable ? "Reachable (:8082)" : "Offline (Qwen)";
          ceoEl.className = ceo.reachable ? "ops-status-ok" : "ops-status-err";
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
        const avgLatency = latencyCount > 0 ? (totalLatency / latencyCount * 1000).toFixed(1) + " ms" : "n/a";

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
    const next = open ?? !consoleEl.classList.contains("open");
    consoleEl.classList.toggle("open", next);
    consoleEl.setAttribute("aria-hidden", next ? "false" : "true");

    if (next) {
      // Close other panels
      const sdca = $("sdca-lab");
      if (sdca) {
        sdca.classList.remove("open");
        sdca.setAttribute("aria-hidden", "true");
      }
      loadDiagnostics();
    }
  }

  window.SZ = window.SZ || {};
  window.SZ.opsConsole = { toggle, loadDiagnostics };
})();
