/* SuperEzio — System health card for the right rail.
 *
 * Renders /health/details, which health.js already fetches every 10s and stores
 * in SZ.state.healthDetails. None of it had a UI, while the rail pooled 49% of
 * empty space at 1440p.
 *
 * Two rules hold everywhere below, and both exist to stop the card from lying:
 *   - a block whose payload is absent is SKIPPED, never filled with a zero the
 *     backend did not send (a "$0.00" nobody measured is worse than a blank);
 *   - a tone is only green when the payload says so. An unrecognised state is
 *     amber, never ok.
 */
(function () {
  "use strict";

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function row(label, value, tone) {
    return (
      '<div class="sysh-row">' +
      '<span class="sysh-row__label">' + esc(label) + "</span>" +
      '<span class="sysh-row__value' + (tone ? " " + tone : "") + '">' + esc(value) + "</span>" +
      "</div>"
    );
  }

  function block(title, rows) {
    if (!rows.length) return "";
    return (
      '<div class="sysh-block">' +
      '<div class="sysh-block__title">' + esc(title) + "</div>" +
      rows.join("") +
      "</div>"
    );
  }

  /* Only "closed" is green. Open and half-open both mean the source is not
     healthy, and an unknown state must never read as ok. */
  function breakerTone(state) {
    var s = String(state || "").toLowerCase();
    if (s === "closed") return "is-ok";
    if (s === "open") return "is-error";
    return "is-warn";
  }

  function providerTone(p) {
    if (!p) return "";
    if (p.reachable === true) return "is-ok";
    var status = String(p.status || "").toLowerCase();
    if (status === "ok" || status === "configured") return "is-ok";
    if (/unconfigured|missing|error|down/.test(status)) return "is-warn";
    return "";
  }

  function breakersBlock(checks) {
    var list = checks.circuit_breakers;
    if (!Array.isArray(list) || !list.length) return "";
    return block(
      "DADOS",
      list.map(function (b) {
        var ok = b.total_successes != null ? b.total_successes : null;
        var bad = b.total_failures != null ? b.total_failures : null;
        var detail = String(b.state || "desconhecido").toUpperCase();
        if (ok != null || bad != null) {
          detail += " · " + (ok == null ? "?" : ok) + " ok / " + (bad == null ? "?" : bad) + " falhas";
        }
        return row(b.circuit || "(sem nome)", detail, breakerTone(b.state));
      })
    );
  }

  function costBlock(checks) {
    var cg = checks.cost_guard;
    if (!cg) return "";
    var rows = [];
    if (cg.cost_today_usd != null && cg.daily_budget_usd != null) {
      rows.push(
        row(
          "Gasto hoje",
          "$" + Number(cg.cost_today_usd).toFixed(2) + " de $" + Number(cg.daily_budget_usd).toFixed(2)
        )
      );
    }
    if (cg.runs_today != null && cg.max_runs_per_day != null) {
      rows.push(row("Runs hoje", cg.runs_today + " de " + cg.max_runs_per_day));
    }
    return block("ORÇAMENTO", rows);
  }

  function providersBlock(checks) {
    var ps = checks.providers_summary;
    if (!ps) return "";
    var rows = [];
    if (ps.primary) {
      rows.push(row((ps.primary.provider || "?") + " · CEO", ps.primary.model || "?", providerTone(ps.primary)));
    }
    if (ps.experts) {
      rows.push(row((ps.experts.provider || "?") + " · experts", ps.experts.model || "?", providerTone(ps.experts)));
    }
    var optional = ps.optional_providers || {};
    Object.keys(optional).forEach(function (key) {
      var p = optional[key] || {};
      rows.push(row(String(key).toUpperCase(), p.status || "?", providerTone(p)));
    });
    return block("PROVIDERS", rows);
  }

  function gpuBlock(checks) {
    var gpu = checks.gpu;
    if (!gpu || !Array.isArray(gpu.devices) || !gpu.devices.length) return "";
    return block(
      "CÉREBRO LOCAL",
      gpu.devices.map(function (d) {
        var used = d.memory_used_mb;
        var total = d.vram_mb;
        var label = String(d.name || "GPU").replace(/^NVIDIA GeForce\s+/i, "");
        if (used == null || !total) return row(label, "VRAM ?");
        var tone = used / total > 0.9 ? "is-warn" : "is-ok";
        return row(label, Math.round(used) + " / " + Math.round(total) + " MB", tone);
      })
    );
  }

  function buildHTML(details) {
    var checks = details && details.checks;
    if (!checks) return '<div class="empty-state">SEM DADO — aguardando /health/details.</div>';
    var html = breakersBlock(checks) + costBlock(checks) + providersBlock(checks) + gpuBlock(checks);
    if (!html) return '<div class="empty-state">SEM DADO — nenhum bloco reconhecido no payload.</div>';
    return html;
  }

  function render() {
    var body = document.getElementById("health-body");
    if (!body) return;
    var details = (window.SZ && window.SZ.state && window.SZ.state.healthDetails) || null;
    body.innerHTML = buildHTML(details);
    var verdict = document.getElementById("health-verdict");
    if (verdict) verdict.textContent = details ? "LIVE" : "--";
  }

  window.SZ = window.SZ || {};
  window.SZ.systemHealth = { buildHTML: buildHTML, render: render };

  if (window.SZ.subscribe) window.SZ.subscribe("operational-snapshot", render);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", render);
  } else {
    render();
  }
})();
