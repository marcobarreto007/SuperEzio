/* ═══════════════════════════════════════════════════════════════
   SuperEzio — AI-NATIVE TRADING WORKBENCH
   Expert cards, real-time state, trust architecture.
   ═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function setText(id, value) { var el = $(id); if (el) el.textContent = value; }
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function safeVal(v, digits) {
    if (v == null || !isFinite(v)) return "N/A";
    digits = digits == null ? 2 : digits;
    return Number(v).toFixed(digits);
  }

  function pct(v) {
    if (v == null || !isFinite(v)) return "N/A";
    return (v * 100).toFixed(0) + "%";
  }

  function mark(el, state) {
    if (!el) return;
    el.classList.remove("is-ok", "is-error", "is-warn");
    if (state) el.classList.add(state);
  }

  function setVerdictEl(id, verdict) {
    var el = $(id);
    if (!el) return;
    el.textContent = verdict || "--";
    el.classList.remove("verdict-pass", "verdict-fail", "verdict-warn", "is-pass", "is-fail", "is-warn", "is-block", "is-allow", "is-bullish", "is-bearish");
    var v = String(verdict || "").toUpperCase();
    if (v === "PASS" || v === "ALLOW" || v === "BULLISH" || v === "BUY") {
      el.classList.add("verdict-pass", "is-pass");
    } else if (v === "FAIL" || v === "BLOCK" || v === "BEARISH" || v === "SELL" || v === "VETO") {
      el.classList.add("verdict-fail", "is-fail");
    } else if (v !== "--" && v !== "WAIT" && v !== "N/A") {
      el.classList.add("verdict-warn", "is-warn");
    }
  }

  function setTrustBar(id, pct, tone) {
    var bar = $(id);
    if (!bar) return;
    var span = bar.querySelector("span");
    if (span) {
      span.style.width = Math.min(100, Math.max(0, (pct || 0) * 100)) + "%";
    }
    bar.classList.remove("is-good", "is-warn", "is-bad");
    if (tone) bar.classList.add(tone);
  }

  /* ── Connection State ── */
  function setConnection(online) {
    var dot = $("sys-dot");
    var label = $("cockpit-connection");
    if (dot) {
      dot.classList.toggle("status-dot--on", Boolean(online));
      dot.classList.toggle("status-dot--off", !online);
      dot.title = online ? "CONECTADO" : "DESCONECTADO";
    }
    if (label) {
      label.classList.toggle("is-online", Boolean(online));
      label.textContent = online ? "CONECTADO" : "DESCONECTADO";
    }
  }

  /* ── Status Bar (kept for compatibility — also updated by status-bar.js) ── */
  function updateStatusBar(data) {
    if (!data) return;
    function getStatus(obj) {
      if (typeof obj === "string") return obj;
      if (obj && typeof obj === "object") return obj.status || "offline";
      return "offline";
    }
    var ceoOk = getStatus(data.ceo) === "online";
    var genieOk = getStatus(data.genie) === "online";
    var deepOk = getStatus(data.deep) === "online" || getStatus(data.deep) === "degraded";
    var ibkrStatus = getStatus(data.ibkr);
    var ibkrOk = ibkrStatus === "online";

    mark($("statusbar-ceo"), ceoOk ? "is-ok" : "is-error");
    setText("statusbar-ceo", "CEO: " + (ceoOk ? "ONLINE" : "OFFLINE"));

    mark($("statusbar-genie"), genieOk ? "is-ok" : "is-error");
    setText("statusbar-genie", "Genie: " + (genieOk ? "online" : "OFFLINE"));

    mark($("statusbar-deep"), deepOk ? "is-ok" : "is-error");
    setText("statusbar-deep", "Deep: " + (deepOk ? "online" : "OFFLINE"));

    mark($("statusbar-ibkr"), ibkrOk ? "is-ok" : "is-warn");
    if (ibkrOk && typeof data.ibkr === "object") {
      var ibkr = data.ibkr;
      var modeLabel = ibkr.paper === true ? "PAPER" : "LIVE";
      var equity = ibkr.equity || "--";
      var positions = ibkr.positions_count == null ? "--" : ibkr.positions_count;
      var orders = ibkr.orders_count == null ? "--" : ibkr.orders_count;
      setText("statusbar-ibkr", "IBKR " + modeLabel + ": $" + equity + " (" + positions + " pos, " + orders + " ord)");
      /* Also update topbar account value */
      updateTopbarAccount(equity, ibkr.unrealized_pnl);
    } else {
      setText("statusbar-ibkr", "IBKR: " + (ibkrOk ? "PAPER" : "OFFLINE"));
    }

    var guards = data.guardrails || {};
    var guardsOk = guards.ok || data.guards_ok || 30;
    var guardsTotal = guards.total || data.guards_total || 30;
    mark($("statusbar-guardrails"), guardsOk >= guardsTotal ? "is-ok" : "is-warn");
    setText("statusbar-guardrails", "Guardrails: " + guardsOk + "/" + guardsTotal);
  }

  function updateTopbarAccount(equity, pnl) {
    var acctEl = $("account-value");
    var pnlEl = $("pnl-value");
    if (acctEl) acctEl.textContent = equity != null ? "$" + safeVal(equity, 2) : "$--";
    if (pnlEl) {
      if (pnl != null && isFinite(pnl)) {
        var sign = pnl >= 0 ? "+" : "";
        pnlEl.textContent = sign + "$" + safeVal(Math.abs(pnl), 2);
        pnlEl.className = "mono topbar__metric-value" + (pnl >= 0 ? " is-positive" : " is-negative");
      } else {
        pnlEl.textContent = "--";
        pnlEl.className = "mono topbar__metric-value";
      }
    }
  }

  /* ── Expert Card Rendering ── */

  /* F51 Verdict Card */
  function renderF51Card(data) {
    if (!data) {
      $("f51-body").innerHTML = '<div class="empty-state">Aguardando veredito F51.</div>';
      setVerdictEl("f51-verdict", "WAIT");
      return;
    }
    var verdict = data.verdict || data.f51_verdict;
    var text = typeof verdict === "object" ? (verdict.verdict || verdict.passed === true ? "PASS" : verdict.passed === false ? "FAIL" : "--") : (verdict || "--");
    var score = data.score != null ? data.score : (verdict && verdict.score);
    var confidence = data.confidence != null ? data.confidence : (verdict && verdict.confidence);
    var factors = (verdict && verdict.factors) || data.factors || {};
    var decisionScore = data.decision_score || (verdict && verdict.decision_score);

    setVerdictEl("f51-verdict", text || "WAIT");

    var scorePct = score != null ? pct(score) : "--";
    var scoreCls = score != null ? (score >= 0.7 ? "is-good" : score >= 0.4 ? "is-warn" : "is-bad") : "";

    var factorRows = [];
    var factorNames = ["veracity", "consensus", "proxy_reward", "robustness", "uncertainty", "danger"];
    var factorLabels = { veracity: "Veracity", consensus: "Consensus", proxy_reward: "Reward", robustness: "Robustness", uncertainty: "Uncertainty", danger: "Danger" };
    factorNames.forEach(function (name) {
      var val = factors[name];
      if (val == null) return;
      var cls = val >= 0.7 ? "is-good" : val >= 0.4 ? "is-warn" : "is-bad";
      if (name === "danger" || name === "uncertainty") {
        cls = val >= 0.7 ? "is-bad" : val >= 0.4 ? "is-warn" : "is-good";
      }
      factorRows.push(
        '<div class="f51-factor ' + cls + '">',
          '<span class="f51-factor__label">' + esc(factorLabels[name]) + '</span>',
          '<div class="f51-factor__track"><i style="width:' + (val * 100) + '%"></i></div>',
          '<span class="f51-factor__val">' + (val * 100).toFixed(0) + '%</span>',
        '</div>'
      );
    });

    var html = '';
    html += '<div class="f51-score-row">';
    html += '<span class="f51-score-badge ' + scoreCls + '">' + esc(scorePct) + '</span>';
    if (confidence != null) {
      html += '<div class="f51-score-stat"><span class="f51-score-stat__label">Confidence</span><span class="f51-score-stat__value">' + esc(pct(confidence)) + '</span></div>';
    }
    if (decisionScore != null) {
      html += '<div class="f51-score-stat"><span class="f51-score-stat__label">Decision</span><span class="f51-score-stat__value">' + esc(safeVal(decisionScore, 3)) + '</span></div>';
    }
    html += '</div>';
    if (factorRows.length) {
      html += '<div class="f51-factors">' + factorRows.join("") + '</div>';
    } else {
      html += '<div class="empty-state">Score: ' + esc(scorePct) + '. No factor details available.</div>';
    }

    $("f51-body").innerHTML = html;

    /* Trust bar: score as confidence indicator */
    var trustPct = score != null ? score : (confidence || 0);
    setTrustBar("f51-trust-bar", trustPct, trustPct >= 0.7 ? "is-good" : trustPct >= 0.4 ? "is-warn" : "is-bad");
  }

  /* SDCA Firewall Card */
  function renderSDCACard(data) {
    if (!data) {
      $("sdca-body").innerHTML = '<div class="empty-state">Aguardando firewall.</div>';
      setVerdictEl("sdca-verdict", "WAIT");
      return;
    }
    var verdict = data.verdict || data.action || data.status || "ALLOW";
    var riskScore = data.risk_score != null ? data.risk_score : data.score;
    var blocking = data.blocking_count != null ? data.blocking_count : data.blocking;
    var fomo = data.fomo_detected || data.fomo;
    var leverage = data.leverage_flag || data.leverage;
    var slippage = data.slippage_risk || data.slippage;
    var freshness = data.signal_freshness || data.freshness;

    setVerdictEl("sdca-verdict", verdict);

    var html = '<div class="sdca-grid">';
    if (riskScore != null) {
      var rsCls = riskScore <= 3 ? "is-good" : riskScore <= 6 ? "is-warn" : "is-bad";
      html += '<div class="sdca-item"><span class="sdca-item__label">Risk Score</span><span class="sdca-item__value ' + rsCls + '">' + esc(safeVal(riskScore, 1)) + '</span></div>';
    }
    if (blocking != null) {
      html += '<div class="sdca-item"><span class="sdca-item__label">Blocking</span><span class="sdca-item__value ' + (blocking > 0 ? "is-bad" : "is-good") + '">' + esc(blocking) + '</span></div>';
    }
    if (fomo != null) {
      html += '<div class="sdca-item"><span class="sdca-item__label">FOMO</span><span class="sdca-item__value ' + (fomo ? "is-bad" : "is-good") + '">' + (fomo ? "DETECTED" : "CLEAN") + '</span></div>';
    }
    if (slippage != null) {
      html += '<div class="sdca-item"><span class="sdca-item__label">Slippage Risk</span><span class="sdca-item__value ' + (slippage ? "is-bad" : "is-good") + '">' + (slippage ? "HIGH" : "LOW") + '</span></div>';
    }
    if (freshness != null) {
      html += '<div class="sdca-item"><span class="sdca-item__label">Signal Age</span><span class="sdca-item__value ' + (freshness === "fresh" ? "is-good" : "is-warn") + '">' + esc(freshness) + '</span></div>';
    }
    html += '</div>';

    if (riskScore == null && blocking == null) {
      html = '<div class="empty-state">Firewall pass. No risk flags raised.</div>';
    }

    $("sdca-body").innerHTML = html;

    var riskNorm = riskScore != null ? Math.min(1, riskScore / 10) : 0.3;
    setTrustBar("sdca-trust-bar", 1 - riskNorm, riskNorm <= 0.3 ? "is-good" : riskNorm <= 0.6 ? "is-warn" : "is-bad");
  }

  /* Neural Decision Card */
  function renderNeuralCard(data) {
    if (!data) {
      $("neural-body").innerHTML = '<div class="empty-state">Aguardando predicao neural.</div>';
      setVerdictEl("neural-verdict", "WAIT");
      return;
    }
    var decision = data.decision || data.action || data.prediction || "HOLD";
    var confidence = data.confidence != null ? data.confidence : data.score;
    var signal = data.signal_strength || data.strength;
    var volatility = data.volatility_regime || data.volatility;
    var regime = data.market_regime || data.regime;

    setVerdictEl("neural-verdict", decision);

    var html = '';
    html += '<div class="neural-row"><span class="neural-row__label">Decision</span><span class="neural-row__value ' + (decision === "BUY" ? "is-buy" : decision === "SELL" ? "is-sell" : "") + '">' + esc(decision) + '</span></div>';
    if (confidence != null) {
      html += '<div class="neural-row"><span class="neural-row__label">Confidence</span><span class="neural-row__value">' + esc(safeVal(confidence, 2)) + '</span></div>';
    }
    if (signal != null) {
      html += '<div class="neural-row"><span class="neural-row__label">Signal Strength</span><span class="neural-row__value ' + (signal >= 0.6 ? "is-buy" : signal <= 0.3 ? "is-sell" : "") + '">' + esc(safeVal(signal, 2)) + '</span></div>';
    }
    if (regime) {
      html += '<div class="neural-row"><span class="neural-row__label">Market Regime</span><span class="neural-row__value">' + esc(regime) + '</span></div>';
    }
    if (volatility != null) {
      html += '<div class="neural-row"><span class="neural-row__label">Volatility Regime</span><span class="neural-row__value ' + (volatility === "low" || volatility < 0.2 ? "is-good" : volatility === "high" || volatility > 0.4 ? "is-bad" : "is-warn") + '">' + esc(typeof volatility === "number" ? safeVal(volatility, 2) : volatility) + '</span></div>';
    }

    $("neural-body").innerHTML = html;

    var trust = confidence != null ? confidence : 0.3;
    setTrustBar("neural-trust-bar", trust, trust >= 0.6 ? "is-good" : trust >= 0.3 ? "is-warn" : "is-bad");
  }

  /* Trinity Deliberation Card */
  function renderTrinityCard(data) {
    if (!data) {
      $("trinity-body").innerHTML = '<div class="empty-state">Sem deliberacao Trinity.</div>';
      setVerdictEl("trinity-verdict", "--");
      setTrustBar("trinity-trust-bar", 0, "");
      return;
    }
    var d = data.data || data;
    var structured = d.structured || {};
    var genie = structured.genie || {};
    var deep = structured.deep || {};
    var bobDecision = structured.bob_decision || data.bob_decision || "WAIT";
    var consensus = data.consensus || structured.consensus || "NO_CONSENSUS";
    var report = d.report || data.deliberation || "";

    setVerdictEl("trinity-verdict", consensus === "CONSENSUS" ? "YES" : consensus);

    var genieV = genie.verdict || genieVerdictFromState() || "WAIT";
    var genieC = genie.confidence || 0;
    var deepV = deep.verdict || deepVerdictFromState() || "WAIT";
    var deepC = deep.confidence || 0;

    var html = '<div class="trinity-grid">';
    html += '<div class="trinity-cell"><span class="trinity-cell__name">Genie</span><span class="trinity-cell__value ' + (String(genieV).toLowerCase()) + '">' + esc(genieV) + '</span></div>';
    html += '<div class="trinity-cell"><span class="trinity-cell__name">Deep</span><span class="trinity-cell__value ' + (String(deepV).toLowerCase()) + '">' + esc(deepV) + '</span></div>';
    html += '<div class="trinity-cell"><span class="trinity-cell__name">Bob</span><span class="trinity-cell__value ' + (String(bobDecision).toLowerCase()) + '">' + esc(bobDecision) + '</span></div>';
    html += '</div>';

    var consensusOk = consensus === "CONSENSUS";
    html += '<div class="trinity-consensus ' + (consensusOk ? "is-yes" : "is-no") + '">' + (consensusOk ? "CONSENSUS ALCANCADO" : "SEM CONSENSO: " + esc(consensus)) + '</div>';

    if (report) {
      html += '<div style="margin-top:4px;font:600 9px/1.4 var(--font-mono);color:var(--text-muted);max-height:48px;overflow:hidden;">' + esc(report.substring(0, 200)) + '</div>';
    }

    $("trinity-body").innerHTML = html;

    setTrustBar("trinity-trust-bar", consensusOk ? 0.85 : 0.3, consensusOk ? "is-good" : "is-warn");
  }

  /* Helper: try to get genie verdict from state */
  function genieVerdictFromState() {
    var experts = (window.SZ.state && window.SZ.state.deep && window.SZ.state.deep.experts) || {};
    for (var k in experts) {
      var v = String(experts[k].verdict || "").toUpperCase();
      if (v.indexOf("BULL") >= 0) return "BULLISH";
      if (v.indexOf("BEAR") >= 0) return "BEARISH";
    }
    return null;
  }

  function deepVerdictFromState() {
    var math = window.SZ.state && window.SZ.state.deep && window.SZ.state.deep.math;
    if (!math) return null;
    var summary = math.summary || {};
    var rsi = summary.rsi || (math.data && math.data.modules && math.data.modules.technical_indicators && math.data.modules.technical_indicators.values && math.data.modules.technical_indicators.values.rsi14);
    if (rsi != null && rsi > 60) return "BULLISH";
    if (rsi != null && rsi < 40) return "BEARISH";
    return "NEUTRAL";
  }

  /* Guardrail Summary Card */
  function renderGuardrailCard(data) {
    if (!data) {
      $("guardrails-body").innerHTML = '<div class="empty-state">Aguardando guardrails.</div>';
      setText("guardrails-summary", "--/30");
      setTrustBar("guardrail-trust-bar", 0, "");
      return;
    }
    var total = data.total_guardrails || data.total || 30;
    var summary = data.summary || {};
    var blocking = summary.blocking_count != null ? summary.blocking_count : 0;
    var okCount = summary.decision_counts ? (summary.decision_counts.ALLOW || 0) : (total - blocking);
    var blockList = summary.blocking_guardrails || [];
    var statusCounts = summary.status_counts || {};
    var decisionCounts = summary.decision_counts || {};

    setText("guardrails-summary", okCount + "/" + total);

    var statusCls = blocking === 0 ? "is-good" : blocking <= 2 ? "is-warn" : "is-bad";

    var html = '<div class="guardrail-strip">';
    html += '<span class="guardrail-chip ' + (blocking === 0 ? "is-pass" : "is-block") + '">' + (blocking === 0 ? "ALL PASS" : blocking + " BLOCKING") + '</span>';
    html += '<span class="guardrail-chip ' + statusCls + '">' + okCount + "/" + total + " OK</span>';

    if (decisionCounts.ALLOW != null) html += '<span class="guardrail-chip is-pass">ALLOW: ' + decisionCounts.ALLOW + '</span>';
    if (decisionCounts.BLOCK != null) html += '<span class="guardrail-chip is-block">BLOCK: ' + decisionCounts.BLOCK + '</span>';
    if (decisionCounts.REVIEW != null) html += '<span class="guardrail-chip is-warn">REVIEW: ' + decisionCounts.REVIEW + '</span>';
    html += '</div>';

    /* Show layers if available from polling format */
    var layers = data.layers || [];
    if (layers.length) {
      html += '<div class="guardrail-layers">';
      layers.forEach(function (layer) {
        var layerCls = layer.ok >= layer.total ? "is-ok" : layer.ok > 0 ? "is-warn" : "is-err";
        html += '<span class="guardrail-layer ' + layerCls + '">' + esc(layer.layer || layer.name || "?") + ' ' + layer.ok + '/' + layer.total + '</span>';
      });
      html += '</div>';
    }

    if (blockList.length) {
      html += '<div class="guardrail-strip" style="margin-top:4px;">';
      blockList.slice(0, 4).forEach(function (id) {
        html += '<span class="guardrail-chip is-block">' + esc(id) + '</span>';
      });
      if (blockList.length > 4) {
        html += '<span class="guardrail-chip is-warn">+' + (blockList.length - 4) + '</span>';
      }
      html += '</div>';
    }

    $("guardrails-body").innerHTML = html;

    var trustPct = okCount / total;
    setTrustBar("guardrail-trust-bar", trustPct, trustPct >= 0.9 ? "is-good" : trustPct >= 0.7 ? "is-warn" : "is-bad");
  }

  /* ── Mangala Compound Tracker Card ── */
  function renderMangalaCard(data) {
    if (!data || data.status === "unavailable" || data.total_flips == null) {
      $("mangala-body").innerHTML = '<div class="empty-state">Aguardando dados do Mangala Tracker.</div>';
      setText("mangala-verdict", "$" + (data && data.starting != null ? data.starting.toFixed(2) : "20.00"));
      setTrustBar("mangala-trust-bar", 0, "");
      return;
    }

    var starting = data.starting || 20.0;
    var current = data.current || 20.0;
    var totalFlips = data.total_flips || 0;
    var winRate = data.win_rate || 0;
    var totalProfit = data.total_profit || 0;
    var bestFlip = data.best_flip;
    var growthPct = data.growth_pct || 0;
    var nextTarget = data.next_target || (starting * 1.5);
    var progressPct = data.progress_pct || 0;

    var currentStr = "$" + current.toFixed(2);
    var profitSign = totalProfit >= 0 ? "+" : "";
    var profitStr = profitSign + "$" + Math.abs(totalProfit).toFixed(2);
    var growthSign = growthPct >= 0 ? "+" : "";
    var growthStr = growthSign + growthPct.toFixed(1) + "%";

    setText("mangala-verdict", currentStr);

    var html = '';
    html += '<div class="mangala-capital-row">';
    html += '  <span class="mangala-capital-label">Starting</span>';
    html += '  <span class="mangala-capital-value">$' + starting.toFixed(2) + '</span>';
    html += '</div>';
    html += '<div class="mangala-capital-row">';
    html += '  <span class="mangala-capital-label">Current</span>';
    html += '  <span class="mangala-capital-value mangala-current">' + esc(currentStr) + '</span>';
    html += '</div>';
    html += '<div class="mangala-stats">';
    html += '  <span class="mangala-stat">' + esc(totalFlips) + ' flips</span>';
    html += '  <span class="mangala-stat">' + esc(winRate) + '% wins</span>';
    html += '  <span class="mangala-stat ' + (totalProfit >= 0 ? 'is-positive' : 'is-negative') + '">' + esc(profitStr) + '</span>';
    html += '</div>';

    /* Progress bar toward next milestone */
    html += '<div class="mangala-progress">';
    html += '  <div class="mangala-progress__label">';
    html += '    <span>Progress to $' + nextTarget.toFixed(2) + '</span>';
    html += '    <span>' + esc(progressPct.toFixed(0)) + '%</span>';
    html += '  </div>';
    html += '  <div class="mangala-progress__track">';
    html += '    <i style="width:' + Math.min(100, Math.max(0, progressPct)) + '%"></i>';
    html += '  </div>';
    html += '</div>';

    /* Best flip detail */
    if (bestFlip && bestFlip.ticker) {
      html += '<div class="mangala-best">';
      html += '  <span class="mangala-best__label">Best flip:</span>';
      html += '  <span class="mangala-best__ticker">' + esc(bestFlip.ticker) + '</span>';
      html += '  <span class="mangala-best__profit">+' + esc(bestFlip.profit.toFixed(2)) + '</span>';
      html += '</div>';
    }

    /* Growth indicator */
    html += '<div class="mangala-growth">';
    html += '  <span class="mangala-growth__label">Growth:</span>';
    html += '  <span class="mangala-growth__value ' + (growthPct >= 0 ? 'is-positive' : 'is-negative') + '">' + esc(growthStr) + '</span>';
    html += '</div>';

    $("mangala-body").innerHTML = html;

    /* Trust bar = progress proxy */
    var trustPct = Math.min(1, Math.max(0, progressPct / 100));
    setTrustBar("mangala-trust-bar", trustPct, trustPct >= 0.5 ? "is-good" : trustPct >= 0.2 ? "is-warn" : "is-bad");
  }

  /* ── Read state and render all cards ── */
  function renderAllCards() {
    var deep = window.SZ.state && window.SZ.state.deep;

    /* F51: from deep state or lastF51Verdict */
    var f51 = deep && deep.f51;
    if (!f51) {
      f51 = window.SZ.state && window.SZ.state.lastF51Verdict;
    }
    renderF51Card(f51 && (f51.data || f51));

    /* SDCA: from deep state or stored in self */
    var sdca = window.SZ.__sdcaState || null;
    renderSDCACard(sdca);

    /* Neural: from deep state or stored in self */
    var neural = window.SZ.__neuralState || null;
    renderNeuralCard(neural);

    /* Trinity: from deep state or lastTrinity */
    var trinity = deep && deep.trinity;
    if (!trinity) trinity = window.SZ.state && window.SZ.state.lastTrinity;
    renderTrinityCard(trinity);

    /* Guardrails: from deep state or lastGuardrailHub or polling status */
    var guardrails = deep && deep.guardrails;
    if (!guardrails) guardrails = window.SZ.state && window.SZ.state.lastGuardrailHub;
    renderGuardrailCard(guardrails);
  }

  /* ── TF Group Button Sync ── */
  function syncTimeframeButtons() {
    var group = $("tf-group");
    var select = $("tf-inp");
    if (!group || !select) return;

    group.addEventListener("click", function (e) {
      var btn = e.target.closest(".tf-btn");
      if (!btn) return;
      var tf = btn.getAttribute("data-tf");
      if (!tf) return;

      /* Update active state on buttons */
      group.querySelectorAll(".tf-btn").forEach(function (b) {
        b.classList.remove("tf-btn--active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("tf-btn--active");
      btn.setAttribute("aria-selected", "true");

      /* Sync hidden select value */
      select.value = tf;

      /* Trigger change event on hidden select so init.js wiring fires loadChart */
      var evt = new Event("change", { bubbles: true });
      select.dispatchEvent(evt);
    });
  }

  /* ── Bob Chat Slide-In Toggle ── */
  function initBobChatToggle() {
    var panel = $("live-panel");
    var tab = $("bob-chat-tab");
    var closeBtn = $("bob-chat-close");
    if (!panel || !tab) return;

    var header = panel.querySelector(".terminal-card-hdr");
    if (header) {
      header.addEventListener("click", function (e) {
        if (e.target.closest("button")) return;
        /* clicking header toggles collapse inside panel, not the slide-in itself */
      });
    }

    tab.addEventListener("click", function (e) {
      e.stopPropagation();
      panel.classList.toggle("is-open");
      tab.setAttribute("aria-label", panel.classList.contains("is-open") ? "Close Bob Chat" : "Open Bob Chat");
    });

    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        panel.classList.remove("is-open");
        tab.setAttribute("aria-label", "Open Bob Chat");
      });
    }

    /* Close on Escape */
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && panel.classList.contains("is-open")) {
        panel.classList.remove("is-open");
        tab.setAttribute("aria-label", "Open Bob Chat");
      }
    });

    /* Start collapsed */
    panel.classList.remove("is-open");
    tab.setAttribute("aria-label", "Open Bob Chat");
  }

  /* ── Pipeline Event Handler ── */
  function handlePipelineEvent(event) {
    if (!event || !event.type) return;

    switch (event.type) {
      case "F51_VERDICT":
        window.SZ.state = window.SZ.state || {};
        window.SZ.state.lastF51Verdict = event;
        renderF51Card(event);
        break;

      case "SDCA_FIREWALL":
        window.SZ.__sdcaState = event;
        renderSDCACard(event);
        break;

      case "NEURAL_DECISION":
        window.SZ.__neuralState = event;
        renderNeuralCard(event);
        break;

      case "TRINITY_DELIBERATION":
        window.SZ.state = window.SZ.state || {};
        window.SZ.state.lastTrinity = event;
        renderTrinityCard(event);
        break;

      case "GUARDRAIL_HUB":
        window.SZ.state = window.SZ.state || {};
        window.SZ.state.lastGuardrailHub = event;
        renderGuardrailCard(event);
        break;

      case "STREAM_START":
        /* Reset cards for new analysis */
        window.SZ.__sdcaState = null;
        window.SZ.__neuralState = null;
        renderF51Card(null);
        renderSDCACard(null);
        renderNeuralCard(null);
        renderTrinityCard(null);
        renderGuardrailCard(null);
        break;

      case "STREAM_END":
        /* Re-read deep state after stream ends — deep-panel.js may have updated */
        renderAllCards();
        break;
    }
  }

  /* ── Main Poll: /cockpit/summary ── */
  function refreshDeepState() {
    /* deep-panel.js populates window.SZ.state.deep via pipeline events.
       This is a fallback poll to catch any missed state. */
    if (window.SZ.deepPanel && window.SZ.deepPanel.render) {
      renderAllCards();
    }
  }

  async function refreshAll() {
    var online = false;
    try {
      var health = await window.SZ.api.fetchHealth();
      online = health && health.status === "ok";
    } catch (e) { online = false; }
    setConnection(online);

    if (!online) {
      updateStatusBar({ ceo: "offline", genie: "offline", deep: "offline", ibkr: "offline" });
      return;
    }

    try {
      var s = await window.SZ.api.fetchCockpitSummary();
      if (!s) return;

      updateStatusBar(s.status || {});

      /* Update cards from deep state (populated by deep-panel.js + events) */
      renderAllCards();

      /* Forward to legacy panels (genie, bob) if they exist */
      if (s.genie && window.SZ.geniePanel && window.SZ.geniePanel.renderFromCockpit) {
        window.SZ.geniePanel.renderFromCockpit(s.genie);
      }
      if (s.bob && window.SZ.bobPanel) {
        if (s.bob.guardrails) {
          var deepState = window.SZ.state && (window.SZ.state.deep = window.SZ.state.deep || {});
          deepState.guardrails = s.bob.guardrails;
        }
        if (s.bob.portfolio && window.SZ.bobPanel) {
          if (window.SZ.renderPortfolioMirror) {
            window.SZ.renderPortfolioMirror(s.bob.portfolio);
          }
        }
      }
    } catch (e) {
      /* silent */
    }
  }

  async function refreshMangala() {
    try {
      var data = await window.SZ.api.fetchMangalaSummary();
      renderMangalaCard(data);
    } catch (e) {
      /* silent — keep last known state */
    }
  }

  /* ── Init ── */
  function init() {
    /* Sync timeframe button group */
    syncTimeframeButtons();

    /* Init Bob Chat slide-in */
    initBobChatToggle();

    /* Subscribe to pipeline events for real-time card updates */
    if (window.SZ.subscribe) {
      window.SZ.subscribe("pipeline-event", handlePipelineEvent);
    }

    /* Initial refresh */
    refreshAll();
    refreshMangala();

    /* Poll every 10 seconds */
    window.setInterval(refreshAll, 10000);

    /* Also poll deep state more frequently for card updates */
    window.setInterval(refreshDeepState, 2000);

    /* Poll Mangala tracker every 15 seconds (trades change less frequently) */
    window.setInterval(refreshMangala, 15000);
  }

  /* ── Public API ── */
  window.SZ = window.SZ || {};
  window.SZ.cockpit = Object.assign(window.SZ.cockpit || {}, {
    refreshAll: refreshAll,
    refreshMangala: refreshMangala,
    updateStatusBar: updateStatusBar,
    renderF51Card: renderF51Card,
    renderSDCACard: renderSDCACard,
    renderNeuralCard: renderNeuralCard,
    renderTrinityCard: renderTrinityCard,
    renderGuardrailCard: renderGuardrailCard,
    renderMangalaCard: renderMangalaCard,
    renderAllCards: renderAllCards,
  });

  document.addEventListener("DOMContentLoaded", init);
})();
