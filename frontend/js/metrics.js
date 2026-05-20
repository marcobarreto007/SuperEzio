/* SuperEzio — Metrics Panel */
(function () {
  function render(data) {
    const uptime = data?.uptime_seconds ? formatUptime(data.uptime_seconds) : "--";
    const counters = data?.counters || {};
    const histograms = data?.histograms || {};

    let html = `<div class="panel-grid">
      <div class="panel-tile panel-tile--ok"><span>Uptime</span><strong>${uptime}</strong></div>
      <div class="panel-tile"><span>Service</span><strong>${data?.service || "?"} v${data?.version || "?"}</strong></div>
    </div>`;

    // Latency histograms
    const latKeys = Object.keys(histograms).filter(k => k.includes("latency"));
    if (latKeys.length) {
      html += '<div style="margin-top:10px"><h3 style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:6px">Latency</h3><div class="panel-grid">';
      latKeys.forEach(k => {
        const h = histograms[k];
        const label = k.replace(/_latency_s/g, "").replace(/_/g, " ");
        html += `<div class="panel-tile"><span>${label}</span><strong>p50: ${ms(h?.p50)} | p95: ${ms(h?.p95)}</strong></div>`;
      });
      html += '</div></div>';
    }

    // Counters
    const errKeys = Object.keys(counters).filter(k => k.includes("error"));
    if (errKeys.length) {
      html += '<div style="margin-top:10px"><h3 style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:6px">Errors</h3><div class="panel-grid">';
      errKeys.forEach(k => {
        html += `<div class="panel-tile panel-tile--${counters[k] > 0 ? 'err' : 'ok'}"><span>${k.replace(/_/g, " ")}</span><strong>${counters[k]}</strong></div>`;
      });
      html += '</div></div>';
    }

    // Token counters
    const tokKeys = Object.keys(counters).filter(k => k.includes("token"));
    if (tokKeys.length) {
      html += '<div style="margin-top:10px"><h3 style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:6px">Tokens</h3><div class="panel-grid">';
      tokKeys.forEach(k => {
        html += `<div class="panel-tile"><span>${k.replace(/_/g, " ")}</span><strong>${(counters[k] || 0).toLocaleString()}</strong></div>`;
      });
      html += '</div></div>';
    }

    return html;
  }

  function ms(s) { return s != null ? (s * 1000).toFixed(0) + "ms" : "--"; }

  function formatUptime(s) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${m}m`;
  }

  async function showPanel() {
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    pc.innerHTML = '<div style="color:var(--muted);font-size:12px;">Loading metrics...</div>';
    try {
      const data = await SZ.api.fetchMetrics();
      SZ.state.metrics = data;
      pc.innerHTML = render(data);
    } catch (e) {
      pc.innerHTML = `<div style="color:var(--red);font-size:12px;">Error: ${e.message}</div>`;
    }
  }

  window.SZ.metrics = { showPanel };
})();
