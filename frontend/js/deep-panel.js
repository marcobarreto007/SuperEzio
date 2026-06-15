/* SuperEzio DeepPanel */
(function () {
  "use strict";

  var ROLE_LABELS = {
    macro_risk: "macro_risk",
    fundamental_value: "fundamental",
    momentum_technical: "momentum",
    contrarian_opportunity: "contrarian",
    sentiment: "sentiment",
    social_forensics: "social_forensics",
  };

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function dig(obj) {
    var cur = obj;
    for (var i = 1; i < arguments.length; i++) {
      if (!cur || typeof cur !== "object") return null;
      cur = cur[arguments[i]];
    }
    return cur == null ? null : cur;
  }

  function number(value, digits) {
    var n = Number(value);
    if (!isFinite(n)) return "N/A";
    return n.toFixed(digits == null ? 2 : digits);
  }

  function money(value) {
    var n = Number(value);
    if (!isFinite(n)) return "N/A";
    return "$" + n.toFixed(2);
  }

  function tone(value) {
    var text = String(value || "").toUpperCase();
    if (text.indexOf("BULL") >= 0 || text.indexOf("RISK_ON") >= 0 || text.indexOf("CLEAN") >= 0 || text.indexOf("ALLOW") >= 0) return "is-good";
    if (text.indexOf("BEAR") >= 0 || text.indexOf("TRAP") >= 0 || text.indexOf("OVER") >= 0 || text.indexOf("BLOCK") >= 0) return "is-bad";
    return "is-warn";
  }

  function parseExpert(event) {
    if (!event || event.ok === false) {
      return {
        role: event && event.role || "expert",
        verdict: "ERROR",
        confidence: 0,
      };
    }
    var raw = String(event.response || "").trim();
    var parsed = null;
    try {
      if (raw.indexOf("```") === 0) {
        raw = raw.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
      }
      parsed = JSON.parse(raw);
    } catch (e) {
      var start = raw.indexOf("{");
      var end = raw.lastIndexOf("}");
      if (start >= 0 && end > start) {
        try { parsed = JSON.parse(raw.slice(start, end + 1)); } catch (_) { parsed = null; }
      }
    }
    parsed = parsed || {};
    return {
      role: event.role || parsed.expert || "expert",
      verdict: parsed.verdict || "RAW",
      confidence: parsed.confidence || 0,
      score: parsed.sentiment_score || parsed.manipulation_score || parsed.score || null,
    };
  }

  function ensureHost() {
    var host = document.querySelector(".chart-workspace");
    if (!host) return null;
    var existing = document.getElementById("deep-runtime");
    if (existing) return existing;
    var runtime = document.createElement("div");
    runtime.id = "deep-runtime";
    runtime.className = "deep-runtime";
    var marketHeader = host.querySelector(".market-header");
    host.insertBefore(runtime, marketHeader || host.firstChild);
    return runtime;
  }

  function mathLine(state) {
    var report = state.math || {};
    var summary = report.summary || {};
    var modules = report.modules || {};
    var ticker = report.ticker || summary.ticker || ((window.SZ.state.chartData || {}).ticker) || "--";
    var chartPrice = dig(window.SZ.state.chartData || {}, "price", "current");
    var latest = summary.latest_price || summary.price || chartPrice;
    var sharpe = summary.sharpe_ratio || summary.sharpe || dig(modules, "risk_metrics", "values", "sharpe_ratio");
    var var95 = summary.var_95 || summary.var95 || dig(modules, "var_parametric", "values", "var_95");
    var dcf = summary.dcf_fair_value || dig(modules, "dcf_proxy", "values", "dcf_value_per_share");
    var kelly = summary.kelly_fraction || dig(modules, "kelly_fraction", "values", "kelly_fraction");
    var crisis = state.crisis || dig(modules, "crisis_aggregate", "values") || {};
    return [
      '<div class="deep-math-grid">',
        '<div><span>Ticker</span><strong>' + esc(ticker) + ' ' + money(latest) + '</strong></div>',
        '<div><span>Sharpe</span><strong>' + esc(number(sharpe, 2)) + '</strong></div>',
        '<div><span>VaR 95</span><strong>' + esc(number(var95, 2)) + '</strong></div>',
        '<div><span>DCF Fair</span><strong>' + esc(money(dcf)) + '</strong></div>',
        '<div><span>Kelly</span><strong>' + esc(number(kelly, 2)) + '</strong></div>',
        '<div><span>Crisis</span><strong>' + esc(crisis.regime || crisis.alert || "NORMAL") + '</strong></div>',
      '</div>',
    ].join("");
  }

  function expertCards(experts) {
    var roles = Object.keys(ROLE_LABELS);
    return '<div class="deep-expert-grid">' + roles.map(function (role) {
      var item = experts[role] || { role: role, verdict: "WAIT", confidence: 0 };
      var label = ROLE_LABELS[role] || role;
      return [
        '<article class="deep-expert-card ' + tone(item.verdict) + '">',
          '<span>' + esc(label) + '</span>',
          '<strong>' + esc(item.verdict || "WAIT") + '</strong>',
          '<em class="mono">' + esc(item.confidence || 0) + '</em>',
        '</article>',
      ].join("");
    }).join("") + '</div>';
  }

  function consensus(experts) {
    var bullish = [];
    var bearish = [];
    var neutral = [];
    Object.keys(experts).forEach(function (role) {
      var verdict = String(experts[role].verdict || "").toUpperCase();
      var label = ROLE_LABELS[role] || role;
      if (verdict.indexOf("BULL") >= 0 || verdict.indexOf("RISK_ON") >= 0 || verdict.indexOf("CLEAN") >= 0) bullish.push(label);
      else if (verdict.indexOf("BEAR") >= 0 || verdict.indexOf("TRAP") >= 0 || verdict.indexOf("OVER") >= 0) bearish.push(label);
      else neutral.push(label);
    });
    return [
      '<div class="deep-consensus">',
        '<div><strong>Concordam (' + bullish.length + '):</strong> ' + esc(bullish.join(", ") || "n/a") + '</div>',
        '<div><strong>Discordam (' + bearish.length + '):</strong> ' + esc(bearish.join(", ") || "n/a") + '</div>',
        '<div><strong>Neutro (' + neutral.length + '):</strong> ' + esc(neutral.join(", ") || "n/a") + '</div>',
      '</div>',
    ].join("");
  }

  function trinityBlock(trinity) {
    if (!trinity || (!trinity.report && !trinity.structured)) {
      return '<div class="cockpit-empty">Sem deliberacao Trinity nesta sessao.</div>';
    }
    var structured = trinity.structured || {};
    var lines = [];
    if (structured.genie) lines.push("Genie: " + (structured.genie.verdict || "?") + " (" + (structured.genie.confidence || 0) + ")");
    if (structured.deep) lines.push("Deep: " + (structured.deep.verdict || "?") + " (" + (structured.deep.confidence || 0) + ")");
    if (structured.bob_decision) lines.push("Bob: " + structured.bob_decision + " | " + (structured.consensus || "NO_CONSENSUS"));
    return '<pre class="deep-trinity-text">' + esc(lines.length ? lines.join("\n") : trinity.report) + '</pre>';
  }

  function render() {
    var host = ensureHost();
    if (!host) return;
    var state = (window.SZ.state.deep = window.SZ.state.deep || { experts: {} });
    host.innerHTML = [
      '<section class="cockpit-section"><div class="cockpit-section__title">Math Summary</div>' + mathLine(state) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Expert Verdicts</div>' + expertCards(state.experts || {}) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Consensus Matrix</div>' + consensus(state.experts || {}) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Trinity Deliberation</div>' + trinityBlock(state.trinity) + '</section>',
    ].join("");
  }

  function handle(event) {
    if (!event || !event.type) return;
    var state = (window.SZ.state.deep = window.SZ.state.deep || { experts: {} });
    if (event.type === "STREAM_START") {
      state.experts = {};
      state.trinity = null;
      state.f51 = null;
      state.crisis = null;
    } else if (event.type === "MATH_REPORT") {
      state.math = event;
    } else if (event.type === "EXPERT_DONE") {
      var expert = parseExpert(event);
      state.experts[expert.role] = expert;
    } else if (event.type === "F51_VERDICT") {
      state.f51 = event;
    } else if (event.type === "CRISIS_MATH") {
      state.crisis = event;
    } else if (event.type === "TRINITY_DELIBERATION") {
      state.trinity = event;
    }
    render();
  }

  function init() {
    ensureHost();
    render();
    if (window.SZ.subscribe) window.SZ.subscribe("pipeline-event", handle);
  }

  window.SZ = window.SZ || {};
  window.SZ.deepPanel = { render: render, handle: handle };
  document.addEventListener("DOMContentLoaded", init);
})();
