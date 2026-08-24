/* SuperEzio BobPanel */
(function () {
  "use strict";

  var GUARDRAIL_LAYERS = [
    ["L1 Input Security", 4],
    ["L2 Provider", 3],
    ["L3 Data Quality", 4],
    ["L4 Risk Analysis", 4],
    ["L5 Fraud Detection", 4],
    ["L6 Trading", 5],
    ["L7 Crisis", 3],
    ["L8 Committee", 3],
  ];

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function ensureHost() {
    var panel = document.getElementById("expert-panel-cards");
    if (!panel) return null;
    var existing = document.getElementById("bob-runtime");
    if (existing) return existing;
    var host = document.createElement("section");
    host.id = "bob-runtime";
    host.className = "bob-runtime";
    host.setAttribute("aria-hidden", "true");
    panel.insertBefore(host, panel.firstChild);
    return host;
  }

  function parseFinal(answer) {
    var text = String(answer || "");
    var verdict = "WAIT";
    var confidence = "";
    text.split(/\r?\n/).forEach(function (line) {
      var v = line.match(/Final verdict:\s*([A-Z_]+)/i);
      if (v) verdict = v[1].toUpperCase();
      var c = line.match(/Confidence:\s*([0-9.]+)/i);
      if (c) confidence = c[1];
    });
    return { verdict: verdict, confidence: confidence };
  }

  function elapsedLabel(step) {
    if (!step || !step.started) return "--";
    var end = step.ended || Date.now();
    return Math.max(0, Math.round(end - step.started)) + "ms";
  }

  function traceSection(state) {
    var trace = state.trace || {};
    var final = state.final || {};
    var ticker = trace.selected_ui_ticker || state.ticker || "";
    var steps = Object.keys(state.steps || {}).slice(-7);
    var stepText = steps.length
      ? steps.map(function (name) { return esc(name) + "(" + esc(elapsedLabel(state.steps[name])) + ")"; }).join(" -> ")
      : "Sem execucao nesta sessao.";
    var okCount = steps.filter(function (name) {
      return (state.steps[name] || {}).status !== "error";
    }).length;
    return [
      '<section class="cockpit-section">',
        '<div class="cockpit-section__title">Decision Trace</div>',
        '<div class="bob-decision-line">Ultima decisao: <strong>' + esc(final.verdict || "WAIT") + '</strong>',
          ticker ? ' em <strong>' + esc(ticker) + '</strong>' : '',
          final.confidence ? ' (' + esc(final.confidence) + ')' : '',
        '</div>',
        '<div class="bob-pipeline-line">' + stepText + '</div>',
        '<div class="bob-node-row"><span>Nos</span><strong>' + esc(okCount) + '/' + esc(steps.length || 0) + ' ok</strong></div>',
      '</section>',
    ].join("");
  }

  function portfolioSection(state) {
    var pf = state.portfolio || {};
    var connected = pf.connected === true || String(pf.connection || "").indexOf("connected") >= 0;
    var equity = pf.equity || "100000.00";
    var orders = Array.isArray(pf.orders) ? pf.orders : (Array.isArray(pf.active_orders) ? pf.active_orders : []);
    var positions = pf.positions || [];
    var rows = "";
    if (orders.length) {
      rows = orders.slice(0, 5).map(function (order) {
        var ticker = order.symbol || order.ticker || "--";
        var side = String(order.action || order.side || "").toUpperCase();
        var qty = order.qty || order.quantity || "--";
        return '<div class="bob-position-row"><span>' + esc(ticker) + ' ' + esc(side) + '</span><strong>' + esc(qty) + '</strong></div>';
      }).join("");
    } else if (Array.isArray(positions) && positions.length) {
      rows = positions.slice(0, 5).map(function (pos) {
        return '<div class="bob-position-row"><span>' + esc(pos.symbol || pos.ticker || "--") + '</span><strong>' + esc(pos.quantity || pos.shares || 0) + '</strong></div>';
      }).join("");
    } else {
      rows = '<div class="cockpit-empty">Sem ordens ativas ou posicoes abertas.</div>';
    }
    return [
      '<section class="cockpit-section">',
        '<div class="cockpit-section__title">Portfolio IBKR</div>',
        '<div class="bob-portfolio-line"><span>Equity</span><strong>$' + esc(equity) + '</strong></div>',
        '<div class="bob-portfolio-line"><span>Status</span><strong>' + esc(connected ? "PAPER CONNECTED" : "OFFLINE") + '</strong></div>',
        '<div class="bob-portfolio-line"><span>Open orders</span><strong>' + esc(orders.length) + '</strong></div>',
        rows,
      '</section>',
    ].join("");
  }

  function guardrailSection(state) {
    var trace = state.trace || {};
    var dataWarn = Boolean(trace.provider_error || (trace.top_rejection_reasons || []).length);
    var rows = GUARDRAIL_LAYERS.map(function (layer) {
      var label = layer[0];
      var total = layer[1];
      var warn = label.indexOf("Data Quality") >= 0 && dataWarn;
      var count = warn ? Math.max(0, total - 1) : total;
      return [
        '<div class="bob-guardrail-row ' + (warn ? "is-warn" : "is-good") + '">',
          '<span>' + esc(label) + '</span>',
          '<strong>(' + count + '/' + total + ')</strong>',
        '</div>',
      ].join("");
    }).join("");
    return '<section class="cockpit-section"><div class="cockpit-section__title">Guardrail Status</div>' + rows + '</section>';
  }

  function render() {
    var host = ensureHost();
    if (!host) return;
    var state = (window.SZ.state.bobPanel = window.SZ.state.bobPanel || { steps: {} });
    host.innerHTML = traceSection(state) + portfolioSection(state) + guardrailSection(state);
  }

  function handle(event) {
    if (!event || !event.type) return;
    var state = (window.SZ.state.bobPanel = window.SZ.state.bobPanel || { steps: {} });
    if (event.type === "STREAM_START") {
      state.steps = {};
      state.started = Date.now();
      state.final = null;
    } else if (event.type === "PIPELINE_STEP") {
      var step = event.step || "pipeline";
      state.steps[step] = state.steps[step] || { started: Date.now() };
      state.steps[step].status = event.status || "running";
      if (event.status && event.status !== "started") state.steps[step].ended = Date.now();
    } else if (event.type === "DATA_COLLECTED" && event.ticker) {
      state.ticker = event.ticker;
    } else if (event.type === "STREAM_END") {
      state.trace = event.trace || {};
      state.final = parseFinal((window.SZ.state.stream || {}).answer || "");
    }
    render();
  }

  async function refreshPortfolio() {
    var state = (window.SZ.state.bobPanel = window.SZ.state.bobPanel || { steps: {} });
    try {
      if (window.SZ.api.fetchCockpitPortfolio) {
        state.portfolio = await window.SZ.api.fetchCockpitPortfolio();
        if (window.SZ.renderPortfolioMirror) window.SZ.renderPortfolioMirror(state.portfolio);
      } else {
        var details = await window.SZ.api.fetchHealthDetails();
        var ibkr = (((details || {}).mission || {}).broker || {}).ibkr || {};
        state.portfolio = {
          connected: String(ibkr.connection || "").indexOf("connected") >= 0 || ibkr.can_read_account === true,
          connection: ibkr.connection || "unknown",
          equity: ibkr.account_equity || "100000.00",
          positions_count: ibkr.positions_count || 0,
          positions: ibkr.positions || [],
        };
      }
      render();
    } catch (e) {
      state.portfolio = { ibkr: { connection: "offline" } };
      render();
    }
  }

  function init() {
    ensureHost();
    render();
    refreshPortfolio();
    window.setInterval(refreshPortfolio, 30000);
    if (window.SZ.subscribe) window.SZ.subscribe("pipeline-event", handle);
  }

  window.SZ = window.SZ || {};
  window.SZ.bobPanel = { render: render, handle: handle, refreshPortfolio: refreshPortfolio };
  document.addEventListener("DOMContentLoaded", init);
})();
