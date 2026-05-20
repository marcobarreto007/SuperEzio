/* SuperEzio — Health + System Info */
(function () {
  async function check() {
    try {
      const h = await SZ.api.fetchHealth();
      SZ.state.health = h.status === "ok";
    } catch (e) { SZ.state.health = false; }
    const dot = document.getElementById("sys-dot");
    if (dot) {
      dot.className = "status-dot " + (SZ.state.health ? "status-dot--on" : "status-dot--off");
      dot.title = SZ.state.health ? "Connected" : "Disconnected";
    }
    SZ.publish("health", SZ.state.health);
  }

  function renderSysInfo(data) {
    const checks = data?.checks || {};
    const rows = [];
    const add = (label, obj, key) => {
      const status = obj?.status || obj?.[key] || "unknown";
      const cls = status === "ok" || status === true ? "ok" : status === "unavailable" || status === "skipped" ? "warn" : "err";
      rows.push(`<div class="panel-tile panel-tile--${cls}"><span>${label}</span><strong>${String(status)}</strong></div>`);
    };

    add("GPU", checks.gpu, "status");
    if (checks.gpu?.available) {
      (checks.gpu.devices || []).forEach(d => {
        rows.push(`<div class="panel-tile panel-tile--ok"><span>GPU ${d.id}</span><strong>${d.name} (${d.vram_mb}MB)</strong></div>`);
      });
    }

    Object.entries(checks.local_models || {}).forEach(([k, v]) => add("Model: " + k, v, "status"));
    add("Redis", checks.redis, "status");

    Object.entries(checks).forEach(([k, v]) => {
      if (k.startsWith("provider_") && typeof v === "object") {
        const cls = v.configured ? "ok" : "warn";
        rows.push(`<div class="panel-tile panel-tile--${cls}"><span>${k.replace("provider_", "")}</span><strong>${v.model || "?"} ${v.configured ? "OK" : "NOT SET"}</strong></div>`);
      }
    });

    const cg = checks.cost_guard;
    if (cg) {
      const budget = cg.budget_remaining_usd != null ? `$${cg.budget_remaining_usd?.toFixed(2)}` : "?";
      rows.push(`<div class="panel-tile panel-tile--ok"><span>Cost Guard</span><strong>${budget} left (${cg.runs_remaining || "?"} runs)</strong></div>`);
    }

    return `<div class="panel-grid">${rows.join("")}</div>`;
  }

  async function showPanel() {
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    pc.innerHTML = '<div style="color:var(--muted);font-size:12px;">Loading system info...</div>';
    try {
      const data = await SZ.api.fetchHealthDetails();
      SZ.state.healthDetails = data;
      pc.innerHTML = renderSysInfo(data);
    } catch (e) {
      pc.innerHTML = `<div style="color:var(--red);font-size:12px;">Error: ${e.message}</div>`;
    }
  }

  window.SZ.health = { check, showPanel };
})();
