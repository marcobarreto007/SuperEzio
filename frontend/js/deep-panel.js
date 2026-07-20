/* SuperEzio DeepPanel — Math, Experts, F51, Guardrails */
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

  function safeVal(v, digits) {
    if (v == null || !isFinite(v)) return "N/A";
    digits = digits == null ? 2 : digits;
    return Number(v).toFixed(digits);
  }

  function pctVal(v) {
    if (v == null || !isFinite(v)) return "N/A";
    return (v * 100).toFixed(1) + "%";
  }

  function money(v) {
    var n = Number(v);
    if (!isFinite(n)) return "N/A";
    return "$" + n.toFixed(2);
  }

  function tone(value) {
    var text = String(value || "").toUpperCase();
    if (text.indexOf("BULL") >= 0 || text.indexOf("RISK_ON") >= 0 || text.indexOf("CLEAN") >= 0 || text.indexOf("ALLOW") >= 0) return "is-good";
    if (text.indexOf("BEAR") >= 0 || text.indexOf("TRAP") >= 0 || text.indexOf("OVER") >= 0 || text.indexOf("BLOCK") >= 0) return "is-bad";
    return "is-warn";
  }

  function decisionClass(decision) {
    if (!decision) return "is-warn";
    var d = String(decision).toUpperCase();
    if (d === "ALLOW" || d === "PASS") return "is-good";
    if (d === "BLOCK" || d === "FAIL" || d === "VETO") return "is-bad";
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
    var host = document.getElementById("deep-panel-body");
    if (host) return host;
    host = document.getElementById("deep-panel") || document.querySelector(".app-main");
    if (!host) return null;
    var existing = document.getElementById("deep-runtime");
    if (existing) return existing;
    var runtime = document.createElement("div");
    runtime.id = "deep-runtime";
    runtime.className = "deep-runtime";
    host.appendChild(runtime);
    return runtime;
  }

  function setStatus(state) {
    var status = document.getElementById("deep-panel-status");
    if (!status) return;
    var experts = Object.keys((state && state.experts) || {}).length;
    var hasMath = Boolean(state && state.math);
    var hasF51 = Boolean(state && state.f51);
    var hasTrinity = Boolean(state && state.trinity);
    var hasGuardrails = Boolean(state && state.guardrails);
    var parts = [];
    if (hasMath) parts.push("MATH");
    if (hasF51) parts.push("F51");
    if (experts) parts.push(experts + "/6 EXP");
    if (hasGuardrails) parts.push("GRD");
    if (hasTrinity) parts.push("TRI");
    status.textContent = parts.length ? parts.join(" | ") : "WAITING";
    status.classList.toggle("cockpit-panel__status--idle", !parts.length);
  }

  /* ─── MATH SECTION ─── */

  function techIndicatorRow(label, value, unit, goodDir) {
    if (value === "N/A" || value == null) return "";
    var dir = "is-warn";
    if (goodDir === "high" && value > 0) dir = "is-good";
    else if (goodDir === "low" && value < 0) dir = "is-bad";
    var cls = typeof value === "number" && isFinite(value)
      ? (value >= 0.6 ? "is-good" : value >= 0.35 ? "is-warn" : "is-bad")
      : "is-warn";
    return '<div class="deep-indicator ' + cls + '"><span>' + esc(label) + '</span><strong>' + esc(safeVal(value, 1)) + (unit || "") + '</strong></div>';
  }

  function bollingerHtml(boll) {
    if (!boll || typeof boll !== "object") return "";
    var upper = safeVal(boll.upper, 2);
    var mid = safeVal(boll.middle || boll.mid, 2);
    var lower = safeVal(boll.lower, 2);
    var width = boll.width != null ? safeVal(boll.width, 1) : null;
    return '<div class="deep-indicator is-warn"><span>Bollinger U/M/L</span><strong>' + upper + " / " + mid + " / " + lower + (width ? " (w:" + width + ")" : "") + '</strong></div>';
  }

  function mathLine(state) {
    var report = state.math || {};
    var data = report.data || report;
    var ticker = data.ticker || ((window.SZ.state && window.SZ.state.ticker) || "--");
    var summary = data.summary || {};
    var modules = data.modules || {};
    var technicals = modules.technical_indicators || {};
    var techVals = technicals.values || {};

    // Build technical indicators grid
    var techRows = [];

    // RSI
    var rsiVal = techVals.rsi14 != null ? safeVal(techVals.rsi14, 1) : null;
    var rsiCls = "is-warn";
    if (rsiVal !== null) {
      var rsiNum = Number(techVals.rsi14);
      rsiCls = rsiNum >= 70 ? "is-bad" : rsiNum <= 30 ? "is-good" : "is-warn";
    }
    techRows.push('<div class="deep-indicator ' + rsiCls + '"><span>RSI (14)</span><strong>' + esc(rsiVal || "N/A") + '</strong></div>');

    // MACD
    var macdVal = techVals.macd;
    var macdLine = macdVal != null ? safeVal(macdVal, 2) : null;
    var macdCls = "is-warn";
    if (macdVal != null) macdCls = macdVal >= 0 ? "is-good" : "is-bad";
    if (macdLine) {
      techRows.push('<div class="deep-indicator ' + macdCls + '"><span>MACD</span><strong>' + esc(macdLine) + '</strong></div>');
    }

    // SMA & EMA
    if (techVals.sma20 != null) techRows.push(techIndicatorRow("SMA20", techVals.sma20, ""));
    if (techVals.sma50 != null) techRows.push(techIndicatorRow("SMA50", techVals.sma50, ""));
    if (techVals.ema20 != null) techRows.push(techIndicatorRow("EMA20", techVals.ema20, ""));

    // Bollinger
    if (techVals.bollinger) {
      techRows.push(bollingerHtml(techVals.bollinger));
    }

    // VWAP
    if (techVals.vwap != null) {
      techRows.push('<div class="deep-indicator is-warn"><span>VWAP</span><strong>' + esc(safeVal(techVals.vwap, 2)) + '</strong></div>');
    }

    // Risk metrics from modules
    var sharpeMod = modules.sharpe_sortino || {};
    var sharpeVals = sharpeMod.values || {};
    var varMod = modules.var_cvar || {};
    var varVals = varMod.values || {};
    var kellyMod = modules.kelly || {};
    var kellyVals = kellyMod.values || {};
    var drawMod = modules.drawdown || {};
    var drawVals = drawMod.values || {};
    var dcfMod = modules.dcf_proxy || {};
    var dcfVals = dcfMod.values || {};
    var crisisMod = modules.crisis_aggregate || {};
    var crisisVals = crisisMod.values || {};

    // Also check summary as fallback
    var sharpe = sharpeVals.sharpe != null ? sharpeVals.sharpe : summary.sharpe;
    var var95 = varVals.var_95 != null ? varVals.var_95 : summary.var_95;
    var kelly = kellyVals.kelly_fraction != null ? kellyVals.kelly_fraction : summary.kelly_fraction;
    var dcf = dcfVals.dcf_value_per_share != null ? dcfVals.dcf_value_per_share : null;
    var maxDD = drawVals.max_drawdown != null ? drawVals.max_drawdown : summary.max_drawdown;
    var volatility = sharpeVals.volatility != null ? sharpeVals.volatility : null;
    var sortino = sharpeVals.sortino != null ? sharpeVals.sortino : null;

    // Price from summary
    var latestPrice = summary.latest_price || data.price;
    var priceStr = latestPrice != null ? "$" + safeVal(latestPrice, 2) : "--";

    // Crisis
    var crisisRegime = crisisVals.regime || crisisVals.alert_level || null;
    var crisisScore = crisisVals.aggregate_score || crisisVals.crisis_score || summary.crisis_score;

    // Risk metrics grid
    var riskRows = [];
    if (sharpe != null) riskRows.push('<div class="deep-metric"><span>Sharpe</span><strong class="' + (sharpe >= 1 ? "is-good" : sharpe >= 0 ? "is-warn" : "is-bad") + '">' + esc(safeVal(sharpe, 2)) + '</strong></div>');
    if (sortino != null) riskRows.push('<div class="deep-metric"><span>Sortino</span><strong>' + esc(safeVal(sortino, 2)) + '</strong></div>');
    if (volatility != null) riskRows.push('<div class="deep-metric"><span>Volatility</span><strong>' + esc(pctVal(volatility)) + '</strong></div>');
    if (var95 != null) riskRows.push('<div class="deep-metric"><span>VaR 95</span><strong class="is-bad">' + esc(safeVal(var95, 2)) + '</strong></div>');
    if (maxDD != null) riskRows.push('<div class="deep-metric"><span>Max DD</span><strong class="is-bad">' + esc(pctVal(maxDD)) + '</strong></div>');
    if (kelly != null) riskRows.push('<div class="deep-metric"><span>Kelly</span><strong>' + esc(pctVal(kelly)) + '</strong></div>');
    if (dcf != null) riskRows.push('<div class="deep-metric"><span>DCF Fair</span><strong>' + esc(money(dcf)) + '</strong></div>');
    if (crisisScore != null) riskRows.push('<div class="deep-metric"><span>Crisis</span><strong class="' + (crisisScore >= 0.7 ? "is-bad" : crisisScore >= 0.4 ? "is-warn" : "is-good") + '">' + esc(safeVal(crisisScore, 2)) + '</strong></div>');

    // Coverage
    var coverage = data.coverage || {};
    var okMods = coverage.ok_modules || 0;
    var totalMods = coverage.total_modules || 0;

    return [
      '<div class="deep-math-header">',
        '<span class="deep-math-ticker">' + esc(ticker) + '</span>',
        '<span class="deep-math-price">' + priceStr + '</span>',
        '<span class="deep-math-coverage">' + okMods + '/' + totalMods + ' mod</span>',
      '</div>',
      '<div class="deep-indicator-grid">' + techRows.join("") + '</div>',
      '<div class="deep-metrics-grid">' + riskRows.join("") + '</div>',
    ].join("");
  }

  /* ─── F51 SECTION ─── */

  function f51Section(state) {
    var f51 = state.f51;
    if (!f51) return '<div class="cockpit-empty">Aguardando veredito F51.</div>';
    var data = f51.data || f51;
    var verdict = data.verdict || data.f51_verdict || data;
    var score = verdict.score != null ? verdict.score : null;
    var verdictText = verdict.verdict || verdict.passed === true ? "PASS" : verdict.passed === false ? "FAIL" : "--";
    var passed = verdict.passed;
    var confidence = verdict.confidence != null ? verdict.confidence : null;
    var factors = verdict.factors || {};
    var decisionScore = verdict.decision_score || data.numbers && data.numbers.f51_decision_score || null;

    var scorePct = score != null ? (score * 100).toFixed(0) + "%" : "--";
    var scoreCls = score != null ? (score >= 0.7 ? "is-good" : score >= 0.4 ? "is-warn" : "is-bad") : "is-warn";

    var factorRows = [];
    var factorNames = ["veracity", "consensus", "proxy_reward", "robustness", "uncertainty", "danger"];
    var factorLabels = { veracity: "Veracity", consensus: "Consensus", proxy_reward: "Proxy Reward", robustness: "Robustness", uncertainty: "Uncertainty", danger: "Danger" };
    factorNames.forEach(function (name) {
      var val = factors[name];
      if (val == null) return;
      var cls = val >= 0.7 ? "is-good" : val >= 0.4 ? "is-warn" : "is-bad";
      if (name === "danger" || name === "uncertainty") {
        cls = val >= 0.7 ? "is-bad" : val >= 0.4 ? "is-warn" : "is-good";
      }
      factorRows.push(
        '<div class="deep-f51-factor ' + cls + '">',
          '<span>' + esc(factorLabels[name]) + '</span>',
          '<div class="deep-f51-track"><i style="width:' + (val * 100) + '%"></i></div>',
          '<strong>' + (val * 100).toFixed(0) + '%</strong>',
        '</div>'
      );
    });

    return [
      '<div class="deep-f51-header">',
        '<div class="deep-f51-badge ' + decisionClass(verdictText) + '">' + esc(String(verdictText).toUpperCase()) + '</div>',
        '<div class="deep-f51-score ' + scoreCls + '"><span>Score</span><strong>' + scorePct + '</strong></div>',
        (decisionScore != null ? '<div class="deep-f51-score"><span>Decision</span><strong>' + esc(safeVal(decisionScore, 3)) + '</strong></div>' : ''),
        (confidence != null ? '<div class="deep-f51-score is-warn"><span>Confidence</span><strong>' + esc(pctVal(confidence)) + '</strong></div>' : ''),
      '</div>',
      '<div class="deep-f51-factors">' + factorRows.join("") + '</div>',
    ].join("");
  }

  /* ─── GUARDRAIL SECTION ─── */

  function guardrailSection(state) {
    var gr = state.guardrails;
    if (!gr) return '<div class="cockpit-empty">Aguardando Guardrail Hub.</div>';

    // Handle two formats:
    // 1. From polling: { ok: N, total: 30, status: "ok", layers: [...] }
    // 2. From pipeline: { total_guardrails: 30, summary: { blocking_count: N, ... } }
    var total = gr.total_guardrails || gr.total || 30;
    var okCount = gr.ok || 0;
    var status = gr.status || "unknown";

    var summary = gr.summary || {};
    var blocking = summary.blocking_count != null ? summary.blocking_count : (total - okCount);
    var blockList = summary.blocking_guardrails || [];
    var statusCounts = summary.status_counts || {};
    var decisionCounts = summary.decision_counts || {};
    var ready = summary.ready !== false;

    // If we have layers from polling, show them
    var layers = gr.layers || [];

    var statusCls = ready ? "is-good" : "is-bad";
    if (blocking > 0) statusCls = "is-bad";
    if (blocking === 0 && okCount > 0) statusCls = "is-good";

    var blockRows = [];
    if (blockList.length) {
      blockList.slice(0, 5).forEach(function (id) {
        blockRows.push('<div class="deep-guardrail-block"><span class="is-bad">BLOCK</span><strong>' + esc(id) + '</strong></div>');
      });
      if (blockList.length > 5) {
        blockRows.push('<div class="deep-guardrail-block"><span>+</span><strong>' + (blockList.length - 5) + ' more</strong></div>');
      }
    }

    // Layer rows from polling format
    var layerRows = [];
    if (layers.length) {
      layers.forEach(function (layer) {
        var layerCls = layer.ok >= layer.total ? "is-good" : layer.ok > 0 ? "is-warn" : "is-bad";
        layerRows.push(
          '<div class="deep-guardrail-block ' + layerCls + '">',
            '<span>' + esc(layer.layer || layer.name || "?") + '</span>',
            '<strong>' + layer.ok + '/' + layer.total + '</strong>',
          '</div>'
        );
      });
    }

    var countParts = [];
    Object.keys(statusCounts).forEach(function (k) {
      countParts.push(k + "=" + statusCounts[k]);
    });
    var countsStr = countParts.join(", ") || (okCount ? okCount + "/" + total + " ok" : "");

    return [
      '<div class="deep-guardrail-header ' + statusCls + '">',
        '<span>Guardrails: ' + total + ' checks</span>',
        '<strong>' + (okCount >= total ? "PASS" : blocking > 0 ? blocking + " BLOCKING" : "DEGRADED") + '</strong>',
      '</div>',
      (countsStr ? '<div class="deep-guardrail-counts"><span>' + esc(countsStr) + '</span></div>' : ''),
      (layerRows.length ? '<div class="deep-guardrail-layers">' + layerRows.join("") + '</div>' : ''),
      (blockRows.length ? '<div class="deep-guardrail-blocks"><div class="cockpit-section__title" style="margin-top:6px">Blocking Guardrails</div>' + blockRows.join("") + '</div>' : ''),
    ].join("");
  }

  /* ─── EXPERT CARDS ─── */

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
    if (!experts || !Object.keys(experts).length) {
      return '<div class="cockpit-empty">Aguardando votos dos experts.</div>';
    }
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
        '<div><strong>Bullish (' + bullish.length + '):</strong> ' + esc(bullish.join(", ") || "n/a") + '</div>',
        '<div><strong>Bearish (' + bearish.length + '):</strong> ' + esc(bearish.join(", ") || "n/a") + '</div>',
        '<div><strong>Neutral (' + neutral.length + '):</strong> ' + esc(neutral.join(", ") || "n/a") + '</div>',
      '</div>',
    ].join("");
  }

  function trinityBlock(trinity) {
    if (!trinity || (!trinity.report && !trinity.structured && !trinity.data)) {
      return '<div class="cockpit-empty">Sem deliberacao Trinity nesta sessao.</div>';
    }
    // Handle raw event vs state
    var data = trinity.data || trinity;
    var structured = data.structured || {};
    var lines = [];
    if (structured.genie) lines.push("Genie: " + (structured.genie.verdict || "?") + " (" + (structured.genie.confidence || 0) + ")");
    if (structured.deep) lines.push("Deep: " + (structured.deep.verdict || "?") + " (" + (structured.deep.confidence || 0) + ")");
    if (structured.bob_decision) lines.push("Bob: " + structured.bob_decision + " | " + (structured.consensus || "NO_CONSENSUS"));
    var reportText = data.report || data.deliberation || "";
    return '<pre class="deep-trinity-text">' + esc(lines.length ? lines.join("\n") : reportText) + '</pre>';
  }

  /* ─── MAIN RENDER ─── */

  function render() {
    var host = ensureHost();
    if (!host) return;
    var state = (window.SZ.state.deep = window.SZ.state.deep || { experts: {} });
    setStatus(state);

    var sections = [];

    // Math
    sections.push(
      '<section class="cockpit-section"><div class="cockpit-section__title">Math & Indicators</div>' +
      mathLine(state) +
      '</section>'
    );

    // F51
    if (state.f51) {
      sections.push(
        '<section class="cockpit-section"><div class="cockpit-section__title">F51 Verdict</div>' +
        f51Section(state) +
        '</section>'
      );
    }

    // Guardrails
    if (state.guardrails) {
      sections.push(
        '<section class="cockpit-section"><div class="cockpit-section__title">Guardrail Hub</div>' +
        guardrailSection(state) +
        '</section>'
      );
    }

    // Experts
    sections.push(
      '<section class="cockpit-section"><div class="cockpit-section__title">Expert Verdicts</div>' +
      expertCards(state.experts || {}) +
      '</section>'
    );

    // Consensus
    sections.push(
      '<section class="cockpit-section"><div class="cockpit-section__title">Consensus Matrix</div>' +
      consensus(state.experts || {}) +
      '</section>'
    );

    // Trinity
    sections.push(
      '<section class="cockpit-section"><div class="cockpit-section__title">Trinity Deliberation</div>' +
      trinityBlock(state.trinity) +
      '</section>'
    );

    host.innerHTML = sections.join("");
  }

  /* ─── EVENT HANDLER ─── */

  function handle(event) {
    if (!event || !event.type) return;
    var state = (window.SZ.state.deep = window.SZ.state.deep || { experts: {} });

    switch (event.type) {
      case "STREAM_START":
        state.experts = {};
        state.trinity = null;
        state.f51 = null;
        state.crisis = null;
        state.math = null;
        state.guardrails = null;
        break;

      case "MATH_REPORT":
        // event is the raw MATH_REPORT payload — data is at top level
        state.math = {
          ticker: event.ticker || "",
          generated_at: event.generated_at || "",
          status: event.status || "partial",
          data: event, // full report
          summary: event.summary || {},
          modules: event.modules || {},
        };
        break;

      case "EXPERT_DONE":
        var expert = parseExpert(event);
        state.experts[expert.role] = expert;
        break;

      case "F51_VERDICT":
        state.f51 = event;
        break;

      case "CRISIS_MATH":
        state.crisis = event;
        break;

      case "GUARDRAIL_HUB":
        state.guardrails = {
          total_guardrails: event.total_guardrails || 30,
          summary: event.summary || {},
        };
        break;

      case "TRINITY_DELIBERATION":
        state.trinity = event;
        break;

      default:
        return; // no render needed
    }

    render();
  }

  /* ─── INIT ─── */

  function init() {
    ensureHost();
    render();
    if (window.SZ.subscribe) window.SZ.subscribe("pipeline-event", handle);
  }

  window.SZ = window.SZ || {};
  window.SZ.deepPanel = { render: render, handle: handle };
  document.addEventListener("DOMContentLoaded", init);
})();
