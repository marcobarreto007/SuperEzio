/* SuperEzio — Boot Sequence */
(function () {
  "use strict";

  function sanitTicker(r) {
    return String(r || "").replace(/[^A-Za-z0-9.\-]/g, "").toUpperCase().substring(0, 12);
  }

  function pct(v) {
    if (v == null || !isFinite(v)) return "—";
    return Math.round(v * 100) + "%";
  }

  function fmt(v, d) {
    if (v == null || !isFinite(v)) return "—";
    d = (d != null) ? d : 2;
    return Number(v).toFixed(d);
  }

  function fmtCompact(v) {
    if (v == null || !isFinite(v)) return "—";
    if (Math.abs(v) >= 1e12)  return (v / 1e12).toFixed(1)  + "T";
    if (Math.abs(v) >= 1e9)   return (v / 1e9).toFixed(1)   + "B";
    if (Math.abs(v) >= 1e6)   return (v / 1e6).toFixed(1)    + "M";
    if (Math.abs(v) >= 1e3)   return (v / 1e3).toFixed(1)    + "K";
    return v.toFixed(2);
  }

  function lastVal(s) {
    if (!s || !s.length) return null;
    for (var i = s.length - 1; i >= 0; i--) {
      var item = s[i];
      var value = (item && typeof item === "object" && "value" in item) ? item.value : item;
      if (value != null && isFinite(value)) return value;
    }
    return null;
  }

  function numOrNull(v) {
    if (v == null) return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  window.SZ = window.SZ || {};
  SZ.sanitTicker = sanitTicker;
  SZ.pct         = pct;
  SZ.fmt         = fmt;
  SZ.fmtCompact  = fmtCompact;
  SZ.lastVal     = lastVal;
  SZ.numOrNull   = numOrNull;

  /* ═══════════════════════════════════════════════════════════════
   * CONTEXT BUILDERS
   * ═══════════════════════════════════════════════════════════════ */

  function buildChartContext() {
    var cd = SZ.state && SZ.state.chartData;
    if (!cd) return "";
    var lines = [];
    lines.push("=== CHART CONTEXT ===");
    var meta = cd.meta || cd.profile || {};
    if (meta) {
      if (meta.name)     lines.push("Asset: " + meta.name);
      if (meta.sector)   lines.push("Sector: " + meta.sector);
      if (meta.exchange) lines.push("Exchange: " + meta.exchange);
    }
    var ohlcv = cd.ohlcv || [];
    if (ohlcv.length) {
      var last = ohlcv[ohlcv.length - 1];
      lines.push("Last close: " + fmt(last && last.close));
      lines.push("Data points: " + ohlcv.length);
    }
    var ind = cd.indicators || {};
    var sma20 = ind.sma_20 || ind.sma20;
    var sma50 = ind.sma_50 || ind.sma50;
    var ema20 = ind.ema_20 || ind.ema20;
    if (sma20)  lines.push("SMA20: "  + fmt(lastVal(sma20)));
    if (sma50)  lines.push("SMA50: "  + fmt(lastVal(sma50)));
    if (ema20)  lines.push("EMA20: "  + fmt(lastVal(ema20)));
    if (ind.rsi) lines.push("RSI: " + fmt(lastVal(ind.rsi)));
    if (ind.macd) lines.push("MACD: " + fmt(lastVal(ind.macd)));
    if (ind.macd_signal) lines.push("MACD Sig: " + fmt(lastVal(ind.macd_signal)));
    if (ind.macd_histogram) lines.push("MACD Hist: " + fmt(lastVal(ind.macd_histogram)));
    lines.push("=== END CHART CONTEXT ===");
    return lines.join("\n");
  }

  function buildPortfolioContext() {
    var pf = SZ.state && SZ.state.portfolio;
    if (!pf) return "";
    var lines = ["=== PORTFOLIO ==="];
    var orders = Array.isArray(pf.orders) ? pf.orders : (Array.isArray(pf.active_orders) ? pf.active_orders : []);
    var positions = Array.isArray(pf.positions) ? pf.positions : [];
    if (orders.length) {
      lines.push("Active IBKR orders:");
      orders.slice(0, 8).forEach(function (order) {
        var ticker = sanitTicker(order.ticker || order.symbol);
        if (!ticker) return;
        lines.push(
          "- " + ticker + " " + String(order.action || order.side || "").toUpperCase() +
          " qty=" + (order.qty || order.quantity || "--") +
          " status=" + (order.status || "--")
        );
      });
    }
    if (positions.length) {
      lines.push("IBKR positions:");
      positions.slice(0, 8).forEach(function (pos) {
        var ticker = sanitTicker(pos.symbol || pos.ticker);
        if (!ticker) return;
        lines.push("- " + ticker + " qty=" + (pos.quantity || pos.qty || pos.shares || "--"));
      });
    }
    if (!orders.length && !positions.length) {
      Object.keys(pf).forEach(function (k) {
        var p = pf[k];
        if (p && p.shares) lines.push(k + ": " + p.shares + " shares");
      });
    }
    if (lines.length === 1) {
      lines.push("No active IBKR orders or positions visible.");
    }
    lines.push("=== END PORTFOLIO ===");
    return lines.join("\n");
  }

  function getBrowserSessionId() {
    var key = "sz_bob_session_id";
    try {
      var existing = localStorage.getItem(key);
      if (existing) return existing;
      var id = "bob-" + (
        window.crypto && crypto.randomUUID
          ? crypto.randomUUID()
          : Date.now() + "-" + Math.random().toString(16).slice(2)
      );
      localStorage.setItem(key, id);
      return id;
    } catch (e) {
      return "bob-" + Date.now();
    }
  }

  function shouldAttachMarketContext(msg, ticker) {
    var raw = String(msg || "").toLowerCase();
    var tk = String(ticker || "").toLowerCase();
    if (!tk) return false;
    if (raw.indexOf(tk) >= 0) return true;
    return /\b(chart|grafico|gráfico|ticker atual|ativo atual|ativo na tela|na tela|no grafico|no gráfico|este ativo|esse ativo|esta acao|esta ação|essa acao|essa ação|this chart|this stock|this asset|current chart|current ticker|current stock|current asset|olhando isso|olhando o grafico|olhando o gráfico|candle|candles|vela|velas|rsi|macd|sma|ema|suporte|resistencia|resistência)\b/i.test(raw);
  }

  function setOpsCard(id, state, text) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("ops-card--ok", "ops-card--warn", "ops-card--err");
    el.classList.add("ops-card--" + state);
    var strong = el.querySelector("strong");
    if (strong) strong.textContent = text;
  }

  async function probeOps() {
    if (!SZ.api) return;
    try {
      await SZ.api.fetchHealth();
      setOpsCard("ops-health", "ok", "Online");
      setOpsCard("ops-bob", "ok", "Reachable");
    } catch (e) {
      setOpsCard("ops-health", "err", "Offline");
      setOpsCard("ops-bob", "err", "Blocked");
    }

    try {
      var cfg = SZ.config || {};
      var ticker = sanitTicker((document.getElementById("ticker-inp") || {}).value || cfg.defaultTicker) || cfg.defaultTicker;
      var tf = (document.getElementById("tf-inp") || {}).value || cfg.defaultTimeframe;
      var data = await SZ.api.fetchChartData(ticker, tf);
      var count = data && data.ohlcv ? data.ohlcv.length : 0;
      setOpsCard("ops-market", count > 0 ? "ok" : "warn", count > 0 ? count + " points" : "No candles");
    } catch (e2) {
      setOpsCard("ops-market", "err", "Failed");
    }

    setOpsCard("ops-stream", window.EventSource ? "ok" : "warn", window.EventSource ? "SSE ready" : "No SSE");
    setOpsCard("ops-risk", SZ.api.evaluateSDCA ? "ok" : "warn", SZ.api.evaluateSDCA ? "Armed" : "Missing");
  }

  SZ.buildChartContext     = buildChartContext;
  SZ.buildPortfolioContext = buildPortfolioContext;

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el && value != null) el.textContent = value;
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function orderTicker(order) {
    return sanitTicker(order && (order.ticker || order.symbol || order.contract_symbol));
  }

  function positionTicker(pos) {
    return sanitTicker(pos && (pos.symbol || pos.ticker));
  }

  function orderList(pf) {
    if (!pf) return [];
    if (Array.isArray(pf.orders)) return pf.orders;
    if (Array.isArray(pf.active_orders)) return pf.active_orders;
    return [];
  }

  function positionList(pf) {
    return pf && Array.isArray(pf.positions) ? pf.positions : [];
  }

  function applyFrontendContent() {
    var cfg = SZ.config || {};
    var content = SZ.content || {};
    var ticker = sanitTicker((SZ.state && SZ.state.ticker) || "");
    var timeframe = cfg.defaultTimeframe || "6M";
    var tickerInput = document.getElementById("ticker-inp");
    if (tickerInput) {
      tickerInput.placeholder = content.chartContextPlaceholder || "Chart";
    }
    var tfInput = document.getElementById("tf-inp");
    if (tfInput) tfInput.value = timeframe;
    setText("logo-sub", content.logoSub);
    setText("live-ticker", ticker || "--");
    setText("workspace-ticker", ticker || "--");
    setText("workspace-tf", timeframe);
    setText("asset-label", content.assetLabel);
    setText("bob-welcome-title", content.bobWelcomeTitle);
    setText("bob-welcome-body", content.bobWelcomeBody);
    setText("sdca-ready", content.sdcaReady);
    setText("sdca-preset-fomo", content.sdcaPresetFomo);
    setText("sdca-preset-safe", content.sdcaPresetSafe);
    setText("ops-label-status", content.ops && content.ops.status);
    setText("ops-label-gpu", content.ops && content.ops.gpu);
    setText("ops-label-redis", content.ops && content.ops.redis);
    setText("ops-label-ceo", content.ops && content.ops.ceo);
    setText("ops-title-capabilities", content.ops && content.ops.capabilities);
    setText("ops-title-manifest", content.ops && content.ops.manifest);
    setText("ops-title-principles", content.ops && content.ops.principles);
    setText("ops-capabilities-loading", content.loading);
    setText("ops-manifest-loading", content.loading);
    setText("ops-health-status", content.statusChecking);
    setText("ops-health-gpu", content.statusChecking);
    setText("ops-health-redis", content.statusChecking);
    setText("ops-health-ceo", content.statusChecking);
    setText("ops-manifest-desc", content.loading);
    var dot = document.getElementById("sys-dot");
    if (dot && content.statusChecking) dot.title = content.statusChecking;
  }

  function getSelectedChartTicker() {
    var typed = sanitTicker(
      (document.getElementById("ticker-inp") || {}).value || ""
    );
    if (typed) return typed;
    if (SZ.state && SZ.state.ticker) return sanitTicker(SZ.state.ticker);
    var cd = SZ.state && SZ.state.chartData;
    if (cd && cd.ticker) return sanitTicker(cd.ticker);
    var pf = SZ.state && SZ.state.portfolio;
    var orders = orderList(pf);
    for (var i = 0; i < orders.length; i++) {
      var ot = orderTicker(orders[i]);
      if (ot) return ot;
    }
    var positions = positionList(pf);
    for (var j = 0; j < positions.length; j++) {
      var pt = positionTicker(positions[j]);
      if (pt) return pt;
    }
    return sanitTicker((pf && pf.selected_ticker) || (SZ.config || {}).defaultTicker || "AAPL");
  }

  function getIbkrFromHealthDetails(details) {
    return (((details || {}).mission || {}).broker || {}).ibkr || {};
  }

  function isPaperTradingActive(details) {
    return (((details || {}).mission || {}).paper_trading || {}).active === true;
  }

  function updateBrokerStatus(details) {
    var btn = document.getElementById("broker-status-btn");
    var label = document.getElementById("broker-status-label");
    if (!btn || !label) return;

    var ibkr = getIbkrFromHealthDetails(details);
    var paperTrading = isPaperTradingActive(details);
    var connection = String(ibkr.connection || "");
    var canRead = ibkr.can_read_account === true || connection.indexOf("connected") >= 0;
    var isPaperPort = ibkr.paper_port === true;
    var canSubmit = ibkr.can_submit_orders === true;
    var paperTrade = paperTrading || (canRead && isPaperPort);
    var state = "unknown";
    var text = "IBKR";
    var title = "IBKR broker link not verified";

    if (canSubmit) {
      state = "trade";
      text = "IBKR TRADE";
      title = "IBKR live order submission enabled. Verify safeguards before use.";
    } else if (paperTrade) {
      state = "trade";
      text = "IBKR PAPER";
      title = "IBKR paper trading active — simulated orders allowed. Training mode.";
    } else if (canRead) {
      state = "read";
      text = "IBKR READ";
      title = "IBKR paper link is connected in read-only/no-orders mode";
    } else if (ibkr.package_present || connection) {
      state = "off";
      text = "IBKR OFF";
      title = "IBKR package is present, but the paper API is not connected";
    }

    btn.classList.remove("broker-chip--unknown", "broker-chip--read", "broker-chip--trade", "broker-chip--off");
    btn.classList.add("broker-chip--" + state);
    btn.title = title;
    btn.setAttribute("aria-label", title);
    label.textContent = text;
  }

  async function refreshBrokerStatus() {
    if (!SZ.api || typeof SZ.api.fetchHealthDetails !== "function") return null;
    try {
      var details = await SZ.api.fetchHealthDetails();
      updateBrokerStatus(details);
      return details;
    } catch (err) {
      updateBrokerStatus({ mission: { broker: { ibkr: { package_present: true, connection: "offline" } } } });
      return null;
    }
  }

  /* ═══════════════════════════════════════════════════════════════
   * TASK SUBMISSION
   * ═══════════════════════════════════════════════════════════════ */

  function buildEnvelope(msg) {
    var ticker = getSelectedChartTicker();
    var tf = (document.getElementById("tf-inp") || {}).value || (SZ.config || {}).defaultTimeframe || "6M";
    var attachMarket = shouldAttachMarketContext(msg, ticker);

    return {
      version: "a2a/1.0",
      from: "user",
      to: "superezio",
      type: "TASK.SUBMIT",
      payload: {
        message: msg,
        ticker: attachMarket ? ticker : "",
        timeframe: tf,
        session_id: getBrowserSessionId(),
        chart_context: attachMarket ? buildChartContext() : "",
        portfolio_context: buildPortfolioContext(),
        rigor: "strict",
        memory_mode: "relevant_all"
      }
    };
  }

  async function submit(msg) {
    if (!msg || !msg.trim()) return;
    msg = msg.trim();

    if (!window.SZ.state) window.SZ.state = {};
    window.SZ.state.trace = {
      user_query: msg,
      detected_intent: "unknown",
      selected_ui_ticker: (document.getElementById("ticker-inp") || {}).value || "",
      chart_context_attached: false,
      route_used: "unknown",
      scanner_invoked: false,
      ceo_called: false,
      fallback_used: false,
      final_content_length: 0,
      candidate_count: 0,
      rejected_count: 0,
      provider_sources_used: []
    };

    var inp = document.getElementById("user-inp");
    var btn = document.getElementById("send-btn");
    if (inp) inp.disabled = true;
    if (btn) btn.disabled = true;

    var welcome = document.querySelector("#chat .bob-welcome");
    if (welcome) welcome.remove();

    /* show user message */
    SZ.chat.addMessage("user");
    var lastMsg = document.getElementById("chat").lastElementChild;
    if (lastMsg) {
      var bubble = lastMsg.querySelector(".msg-bubble");
      if (bubble) bubble.textContent = msg;
    }

    var envelope = buildEnvelope(msg);
    var t0 = performance.now();

    try {
      var resp = await SZ.api.submitTask(envelope);
      var lat = Math.round(performance.now() - t0);
      var latEl = document.getElementById("hud-latency");
      if (latEl) latEl.textContent = lat;

      var reader  = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer  = "";

      while (true) {
        var result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });

        var lines = buffer.split("\n");
        buffer = lines.pop();

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line) continue;
          var ev = null;
          try {
            ev = JSON.parse(line);
          } catch (parseErr) {
            console.warn("[SZ] NDJSON parse:", parseErr, line);
            continue;
          }
          try {
            if (SZ.handleEvent) SZ.handleEvent(ev);
          } catch (handlerErr) {
            console.warn("[SZ] event handler:", handlerErr, ev);
          }
          if (window.scheduler && typeof window.scheduler.yield === "function") {
            await window.scheduler.yield();
          }
        }
      }

      if (buffer.trim()) {
        try {
          var ev2 = JSON.parse(buffer.trim());
          if (SZ.handleEvent) {
            try { SZ.handleEvent(ev2); } catch (handlerErr2) { console.warn("[SZ] event handler:", handlerErr2, ev2); }
          }
        } catch (e) { console.warn("[SZ] NDJSON parse:", e, buffer.trim()); }
      }

    } catch (err) {
      console.error("[SZ] submit error:", err);
      if (SZ.handleEvent) {
        SZ.handleEvent({ type: "ERROR", message: "Connection error: " + err.message });
        SZ.handleEvent({ type: "STREAM_END" });
      }
      if (inp) inp.disabled = false;
      if (btn) btn.disabled = false;
    } finally {
      if (inp) inp.disabled = false;
      if (btn) btn.disabled = false;
    }
  }

  /* ═══════════════════════════════════════════════════════════════
   * CHART & LIVE
   * ═══════════════════════════════════════════════════════════════ */

  function markSelectedMirrorTicker(ticker) {
    var rows = document.querySelectorAll(".order-row[data-order-ticker]");
    var selected = sanitTicker(ticker);
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle(
        "is-selected",
        sanitTicker(rows[i].getAttribute("data-order-ticker")) === selected
      );
    }
  }

  function renderOrderButton(item, kind, selected) {
    var ticker = kind === "position" ? positionTicker(item) : orderTicker(item);
    if (!ticker) return "";
    var action = String(item.action || item.side || (kind === "position" ? "POS" : "ORDER")).toUpperCase();
    var qty = item.qty || item.quantity || item.shares || "--";
    var status = item.status || (kind === "position" ? "OPEN" : "PENDING");
    var price = item.limit_price || item.lmtPrice || item.entry_price || item.avgCost;
    var meta = kind === "position"
      ? "position qty " + qty + (price ? " avg " + fmt(Number(price), 2) : "")
      : (item.order_type || item.orderType || "LMT") + " qty " + qty + (price ? " @ " + fmt(Number(price), 2) : "");
    return [
      '<button class="order-row ' + (selected === ticker ? "is-selected" : "") + '" type="button"',
        ' data-order-kind="' + esc(kind) + '"',
        ' data-order-id="' + esc(item.order_id || item.id || "") + '"',
        ' data-order-ticker="' + esc(ticker) + '">',
        '<span class="order-row__ticker">' + esc(ticker) + '</span>',
        '<span class="order-row__side">' + esc(action) + '</span>',
        '<span class="order-row__status">' + esc(status) + '</span>',
        '<span class="order-row__meta">' + esc(meta) + '</span>',
      '</button>',
    ].join("");
  }

  function renderPortfolioMirror(portfolio) {
    if (!window.SZ.state) window.SZ.state = {};
    SZ.state.portfolio = portfolio || {};
    var host = document.getElementById("orders-list");
    var countEl = document.getElementById("orders-count");
    if (!host) return false;

    var pf = SZ.state.portfolio;
    var orders = orderList(pf);
    var positions = positionList(pf);
    var current = sanitTicker(SZ.state.ticker || (document.getElementById("ticker-inp") || {}).value || "");
    var firstTicker = "";
    var rows = [];

    orders.forEach(function (order) {
      var ticker = orderTicker(order);
      if (!firstTicker && ticker) firstTicker = ticker;
      rows.push(renderOrderButton(order, "order", current));
    });

    if (!orders.length) {
      positions.forEach(function (pos) {
        var ticker = positionTicker(pos);
        if (!firstTicker && ticker) firstTicker = ticker;
        rows.push(renderOrderButton(pos, "position", current));
      });
    }

    var visibleRows = rows.filter(Boolean);
    var count = orders.length || positions.length || 0;
    if (countEl) countEl.textContent = String(count);
    if (visibleRows.length) {
      host.innerHTML = visibleRows.join("");
    } else {
      host.innerHTML = '<div class="cockpit-empty">No active IBKR orders. Manual chart remains available.</div>';
    }

    var buttons = host.querySelectorAll(".order-row[data-order-ticker]");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener("click", function () {
        selectTicker(this.getAttribute("data-order-ticker"), "ibkr_mirror_click", {
          order_id: this.getAttribute("data-order-id") || "",
          kind: this.getAttribute("data-order-kind") || "order"
        });
      });
    }

    if (!current && (firstTicker || pf.selected_ticker)) {
      selectTicker(firstTicker || pf.selected_ticker, "ibkr_mirror_boot", null);
      return true;
    }
    markSelectedMirrorTicker(current);
    return Boolean(current);
  }

  async function refreshCockpitPortfolio() {
    if (!SZ.api || typeof SZ.api.fetchCockpitPortfolio !== "function") return false;
    try {
      var portfolio = await SZ.api.fetchCockpitPortfolio();
      return renderPortfolioMirror(portfolio);
    } catch (err) {
      renderPortfolioMirror({ orders: [], positions: [] });
      return false;
    }
  }

  function selectTicker(ticker, reason, meta) {
    ticker = sanitTicker(ticker);
    if (!ticker) return false;
    if (!window.SZ.state) window.SZ.state = {};
    SZ.state.ticker = ticker;
    SZ.state.selectedTickerSource = reason || "manual";
    SZ.state.selectedOrder = meta || null;
    var tickerInput = document.getElementById("ticker-inp");
    if (tickerInput) tickerInput.value = ticker;
    setText("workspace-ticker", ticker);
    setText("live-ticker", ticker);
    markSelectedMirrorTicker(ticker);
    loadChart(ticker);
    return true;
  }

  async function loadChart(tickerOverride) {
    if (tickerOverride && typeof tickerOverride === "object") tickerOverride = "";
    var ticker = sanitTicker(tickerOverride || getSelectedChartTicker());
    var tf = (document.getElementById("tf-inp") || {}).value || (SZ.config || {}).defaultTimeframe || "6M";
    if (!ticker) return;
    if (!window.SZ.state) window.SZ.state = {};
    SZ.state.ticker = ticker;

    var t0 = performance.now();
    try {
      var data = await SZ.api.fetchChartData(ticker, tf);
      var lat = Math.round(performance.now() - t0);
      var latEl = document.getElementById("hud-latency");
      if (latEl) latEl.textContent = lat;
      SZ.state.chartData = data;
      updateWorkspaceLabels(data, ticker, tf);
      markSelectedMirrorTicker(ticker);
      if (SZ.renderProfile)   SZ.renderProfile();
      if (SZ.renderChart)     SZ.renderChart();
      if (SZ.drawLiveCandles) SZ.drawLiveCandles();
    } catch (err) {
      console.error("[SZ] loadChart:", err);
    }
  }

  function updateWorkspaceLabels(data, ticker, tf) {
    var price = data && data.price ? data.price : {};
    var resolvedTicker = (data && data.ticker) || ticker || "";
    var ids = ["workspace-ticker", "live-ticker", "side-ticker"];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el) el.textContent = resolvedTicker || "--";
    }
    var tfEl = document.getElementById("workspace-tf");
    if (tfEl) tfEl.textContent = tf || "";
    var priceEl = document.getElementById("live-price");
    if (priceEl) priceEl.textContent = price.current != null ? fmt(price.current, 2) : "--";
    var changeEl = document.getElementById("live-change");
    if (changeEl) {
      var cp = numOrNull(price.change_pct);
      changeEl.textContent = cp != null ? (cp >= 0 ? "+" : "") + fmt(cp, 2) + "%" : "--";
      changeEl.style.color = cp == null ? "" : cp >= 0 ? "#00c853" : "#ff1744";
    }
  }

  function toggleLive() {
    var ticker = getSelectedChartTicker();
    var tf = (document.getElementById("tf-inp") || {}).value || "1D";
    if (!SZ.live) return;

    var statusEl = document.getElementById("live-status");
    var isLive = statusEl && statusEl.textContent === "LIVE";
    if (isLive) {
      SZ.live.stop();
    } else if (ticker) {
      SZ.live.start(ticker, tf);
    }
  }

  /* ═══════════════════════════════════════════════════════════════
   * WORKSPACE MODES
   * ═══════════════════════════════════════════════════════════════ */

  /* ═══════════════════════════════════════════════════════════════
   * DOM WIRING
   * ═══════════════════════════════════════════════════════════════ */

  function wireEvents() {
    var hasFieldSizing = window.CSS && CSS.supports && CSS.supports("field-sizing", "content");

    /* SEND button */
    var sendBtn = document.getElementById("send-btn");
    if (sendBtn) {
      sendBtn.addEventListener("click", function () {
        var inp = document.getElementById("user-inp");
        if (inp && inp.value.trim()) {
          submit(inp.value);
          inp.value = "";
          if (!hasFieldSizing) {
            inp.style.height = "auto";
          }
        }
      });
    }

    /* USER_INP keydown Enter */
    var userInp = document.getElementById("user-inp");
    if (userInp) {
      userInp.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (userInp.value.trim()) {
            submit(userInp.value);
            userInp.value = "";
            if (!hasFieldSizing) {
              userInp.style.height = "auto";
            }
          }
        }
      });
      if (!hasFieldSizing) {
        userInp.addEventListener("input", function () {
          userInp.style.height = "auto";
          userInp.style.height = Math.min(userInp.scrollHeight, 160) + "px";
        });
      }
    }

    /* TICKER / TF change */
    var tickerInp = document.getElementById("ticker-inp");
    if (tickerInp) {
      tickerInp.addEventListener("change", function () {
        selectTicker(tickerInp.value, "manual", null);
      });
    }
    var tfInp = document.getElementById("tf-inp");
    if (tfInp) {
      tfInp.addEventListener("change", loadChart);
    }

    /* LIVE toggle */
    var liveBtn = document.getElementById("live-btn");
    if (liveBtn) {
      liveBtn.addEventListener("click", toggleLive);
    }

    /* CHART button */
    var chartBtn = document.getElementById("chart-btn");
    if (chartBtn) {
      chartBtn.addEventListener("click", loadChart);
    }

    var brokerBtn = document.getElementById("broker-status-btn");
    if (brokerBtn) {
      brokerBtn.addEventListener("click", function () {
        refreshBrokerStatus();
        if (SZ.opsConsole && typeof SZ.opsConsole.toggle === "function") {
          SZ.opsConsole.toggle(true);
        }
      });
    }

    /* SDCA Lab toggle */
    var sdcaLabBtn = document.getElementById("sdca-lab-btn");
    if (sdcaLabBtn) {
      sdcaLabBtn.addEventListener("click", function () {
        if (SZ.sdcaLab && typeof SZ.sdcaLab.toggle === "function") {
          SZ.sdcaLab.toggle();
          return;
        }
        var panel = document.getElementById("sdca-lab");
        if (panel) panel.classList.toggle("open");
      });
    }
    var sdcaLabClose = document.getElementById("sdca-lab-close");
    if (sdcaLabClose) {
      sdcaLabClose.addEventListener("click", function () {
        if (SZ.sdcaLab && typeof SZ.sdcaLab.toggle === "function") {
          SZ.sdcaLab.toggle(false);
          return;
        }
        var panel = document.getElementById("sdca-lab");
        if (panel) panel.classList.remove("open");
      });
    }
    /* Ops Console toggle */
    var opsBtn = document.getElementById("ops-console-btn");
    if (opsBtn) {
      opsBtn.addEventListener("click", function () {
        if (SZ.opsConsole && typeof SZ.opsConsole.toggle === "function") {
          SZ.opsConsole.toggle();
        }
      });
    }
    var opsClose = document.getElementById("ops-console-close");
    if (opsClose) {
      opsClose.addEventListener("click", function () {
        if (SZ.opsConsole && typeof SZ.opsConsole.toggle === "function") {
          SZ.opsConsole.toggle(false);
        }
      });
    }
    /* Portfolio toggle */
    var pfBtn = document.getElementById("pf-btn");
    if (pfBtn) {
      pfBtn.addEventListener("click", function () {
        var drawer = document.getElementById("portfolio-drawer");
        if (drawer) {
          var open = drawer.style.display !== "none";
          drawer.style.display = open ? "none" : "flex";
        }
      });
    }

    var askButtons = document.querySelectorAll("[data-ask]");
    for (var i = 0; i < askButtons.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () {
          var inp = document.getElementById("user-inp");
          if (!inp) return;
          inp.value = btn.getAttribute("data-ask") || "";
          inp.focus();
          inp.dispatchEvent(new Event("input"));
        });
      })(askButtons[i]);
    }

    var modes = document.querySelectorAll("[data-mode]");
    for (var j = 0; j < modes.length; j++) {
      (function (mode) {
        mode.addEventListener("click", function () {
          for (var k = 0; k < modes.length; k++) modes[k].classList.remove("active");
          mode.classList.add("active");
          var name = mode.getAttribute("data-mode");
          if (name === "bob" && userInp) userInp.focus();
          if (name === "risk") {
            var panel = document.getElementById("sdca-lab");
            if (panel) panel.classList.add("open");
          }
          if (name === "streams") toggleLive();
          if (name === "markets" && tickerInp) tickerInp.focus();
        });
      })(modes[j]);
    }
  }

  /* ═══════════════════════════════════════════════════════════════
   * BOOT
   * ═══════════════════════════════════════════════════════════════ */

  function boot() {
    applyFrontendContent();

    /* load portfolio from localStorage */
    try {
      var stored = localStorage.getItem("sz_portfolio");
      if (stored) {
        var parsed = JSON.parse(stored);
        if (typeof parsed === "object") SZ.state.portfolio = parsed;
      }
    } catch (e) { /* ignore */ }

    /* load journal from localStorage */
    try {
      var journalStr = localStorage.getItem("sz_journal");
      if (journalStr) {
        var journalParsed = JSON.parse(journalStr);
        if (Array.isArray(journalParsed)) SZ.state.journal = journalParsed;
      }
    } catch (e) { /* ignore */ }

    wireEvents();

    /* health check */
    if (SZ.api && SZ.api.fetchHealth) {
      SZ.api.fetchHealth().then(function (data) {
        SZ.state.health = true;
        var dot = document.getElementById("sys-dot");
        if (dot) {
          dot.classList.remove("status-dot--off");
          dot.classList.add("status-dot--on");
          dot.title = "Online";
        }
      }).catch(function () { /* silent */ });
    }

    /* auto-focus */
    var userInp = document.getElementById("user-inp");
    if (userInp) userInp.focus();

    /* init Lucide icons */
    if (window.lucide) lucide.createIcons();

    refreshCockpitPortfolio().then(function (selected) {
      if (!selected && !(SZ.state && SZ.state.chartData)) loadChart();
    });
    refreshBrokerStatus();
    probeOps();

    console.log("[SZ] Boot complete.");
  }

  SZ.init    = boot;
  SZ.submit  = submit;
  SZ.loadChart = loadChart;
  SZ.selectTicker = selectTicker;
  SZ.renderPortfolioMirror = renderPortfolioMirror;
  SZ.refreshCockpitPortfolio = refreshCockpitPortfolio;
  SZ.refreshBrokerStatus = refreshBrokerStatus;
  SZ.updateBrokerStatus = updateBrokerStatus;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
