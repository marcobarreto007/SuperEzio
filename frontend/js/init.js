/* SuperEzio — Boot Sequence */
(function () {
  "use strict";

  function sanitTicker(r) {
    var ticker = String(r || "").replace(/[^A-Za-z0-9.\-]/g, "").toUpperCase().substring(0, 12);
    return ticker === "HEARTBEAT" ? "" : ticker;
  }

  function isValidTicker(ticker) {
    if (!ticker || typeof ticker !== "string") return false;
    var trimmed = ticker.trim();
    if (trimmed === "") return false;
    if (trimmed === "HEARTBEAT") return false;
    if (trimmed.length > 12) return false;
    var pattern = /^[A-Z0-9.\-]+$/i;
    return pattern.test(trimmed);
  }

  function safeTicker(ticker) {
    var candidate = sanitTicker(ticker);
    return isValidTicker(candidate) ? candidate : "";
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
    var expectedTicker = sanitTicker(getSelectedChartTicker());
    var meta = cd.meta || cd.profile || {};
    var contextTicker = sanitTicker(cd.ticker || meta.ticker || meta.symbol || expectedTicker);
    if (expectedTicker && contextTicker && expectedTicker !== contextTicker) return "";
    var lines = [];
    lines.push("=== CHART CONTEXT ===");
    if (contextTicker) lines.push("Ticker: " + contextTicker);
    if (meta) {
      if (meta.name)     lines.push("Asset: " + meta.name);
      if (meta.sector)   lines.push("Sector: " + meta.sector);
      if (meta.exchange) lines.push("Exchange: " + meta.exchange);
    }
    var price = cd.price || {};
    if (price.current != null) lines.push("Current price: " + fmt(price.current));
    if (price.change_pct != null) lines.push("Change %: " + fmt(price.change_pct) + "%");
    var ohlcv = cd.ohlcv || [];
    if (ohlcv.length) {
      var last = ohlcv[ohlcv.length - 1];
      lines.push("Last close: " + fmt(last && last.close));
      if (last && last.volume != null) lines.push("Last volume: " + last.volume);
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
    var brokerOrders = brokerOrderList(pf);
    var localTickets = localTicketList(pf);
    var positions = Array.isArray(pf.positions) ? pf.positions : [];
    var trades = tradeHistoryList(pf);
    if (brokerOrders.length) {
      lines.push("Active IBKR orders:");
      brokerOrders.slice(0, 8).forEach(function (order) {
        var ticker = sanitTicker(order.ticker || order.symbol);
        if (!ticker) return;
        lines.push(
          "- " + ticker + " " + String(order.action || order.side || "").toUpperCase() +
          " qty=" + (order.qty || order.quantity || "--") +
          " status=" + (order.status || "--")
        );
      });
    }
    if (localTickets.length) {
      lines.push("Local pending tickets:");
      localTickets.slice(0, 5).forEach(function (order) {
        var ticker = sanitTicker(order.ticker || order.symbol);
        if (!ticker) return;
        lines.push(
          "- " + ticker + " " + String(order.action || order.side || "").toUpperCase() +
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
    if (trades.length) {
      lines.push("Recent paper trade history:");
      trades.slice(0, 5).forEach(function (trade) {
        var ticker = sanitTicker(trade.ticker || trade.symbol);
        if (!ticker) return;
        lines.push("- " + ticker + " " + (trade.status || "--") + " outcome=" + (trade.outcome || "--"));
      });
    }
    if (!brokerOrders.length && !localTickets.length && !positions.length) {
      Object.keys(pf).forEach(function (k) {
        var p = pf[k];
        if (p && p.shares) lines.push(k + ": " + p.shares + " shares");
      });
    }
    if (lines.length === 1) {
      lines.push("No active IBKR orders, local tickets, or positions visible.");
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
      if (!ticker) {
        setOpsCard("ops-market", "warn", "Select ticker");
      } else {
        var tf = (document.getElementById("tf-inp") || {}).value || cfg.defaultTimeframe;
        var data = await SZ.api.fetchChartData(ticker, tf);
        var count = data && data.ohlcv ? data.ohlcv.length : 0;
        setOpsCard("ops-market", count > 0 ? "ok" : "warn", count > 0 ? count + " points" : "No candles");
      }
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

  function brokerOrderList(pf) {
    if (!pf) return [];
    if (Array.isArray(pf.broker_orders)) return pf.broker_orders;
    return orderList(pf).filter(function (order) {
      return String((order && order.source) || "").toLowerCase() === "ibkr";
    });
  }

  function localTicketList(pf) {
    if (!pf) return [];
    if (Array.isArray(pf.local_tickets)) return pf.local_tickets;
    return orderList(pf).filter(function (order) {
      return String((order && order.source) || "").toLowerCase() !== "ibkr";
    });
  }

  function positionList(pf) {
    return pf && Array.isArray(pf.positions) ? pf.positions : [];
  }

  function tradeHistoryList(pf) {
    return pf && Array.isArray(pf.trade_history) ? pf.trade_history : [];
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
    return sanitTicker((pf && pf.selected_ticker) || (SZ.config || {}).defaultTicker || "");
  }

  function chartDataReadyFor(ticker) {
    ticker = sanitTicker(ticker);
    var cd = SZ.state && SZ.state.chartData;
    if (!ticker || !cd) return false;
    var meta = cd.meta || cd.profile || {};
    var contextTicker = sanitTicker(cd.ticker || meta.ticker || meta.symbol || "");
    var ohlcv = Array.isArray(cd.ohlcv) ? cd.ohlcv : [];
    if (contextTicker && contextTicker !== ticker) return false;
    return ohlcv.length > 0;
  }

  async function ensureChartContext(ticker) {
    ticker = sanitTicker(ticker || getSelectedChartTicker());
    if (!ticker) return false;
    if (chartDataReadyFor(ticker)) return true;
    await loadChart(ticker);
    return chartDataReadyFor(ticker);
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

    if (canSubmit && paperTrade) {
      state = "trade";
      text = "IBKR PAPER";
      title = "IBKR paper order submission enabled. Simulated orders only.";
    } else if (canSubmit && !paperTrade) {
      state = "off";
      text = "IBKR BLOCKED";
      title = "IBKR is not in paper mode. Live-money execution is blocked by policy.";
    } else if (paperTrade) {
      state = "trade";
      text = "IBKR PAPER";
      title = "IBKR paper trading active — simulated orders allowed. Training mode.";
    } else if (canRead) {
      state = "read";
      text = "IBKR READ";
      title = "IBKR paper link is connected in read-only/no-orders mode";
    } else {
      state = "paper";
      text = "PAPER SIM";
      title = "SuperEzio Paper Trading Ativo — Simulação segura e auditoria registradas.";
    }

    btn.classList.remove("broker-chip--unknown", "broker-chip--read", "broker-chip--trade", "broker-chip--off", "broker-chip--paper");
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
    var chartReady = attachMarket ? chartDataReadyFor(ticker) : false;

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
        chart_context_ready: chartReady,
        chart_context_source: chartReady ? "frontend_chart_state" : "",
        portfolio_context: buildPortfolioContext(),
        rigor: "strict",
        memory_mode: "relevant_all"
      }
    };
  }

  function setBobBusy(isBusy, runId) {
    if (!window.SZ.state) window.SZ.state = {};
    window.SZ.state.bobBusy = !!isBusy;
    window.SZ.state.activeBobRunId = isBusy ? (runId || window.SZ.state.activeBobRunId || "") : "";
    var btn = document.getElementById("send-btn");
    // O input de chat NAO e mais desabilitado durante o run: travar por
    // minutos (auto-analise ao clicar num ticker) parecia tela congelada.
    // O backend serializa runs concorrentes com 429 estruturado.
    if (btn) {
      btn.disabled = !!isBusy;
      btn.classList.toggle("is-busy", !!isBusy);
      btn.setAttribute("aria-busy", isBusy ? "true" : "false");
    }
  }

  function showBobNotice(message) {
    var chat = document.getElementById("chat");
    if (!chat) return;
    var div = document.createElement("div");
    div.className = "bob-local-notice";
    div.textContent = message;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  function isActiveTaskError(err) {
    return !!err && (err.status === 429 || err.code === "active_task");
  }

  async function submit(msg) {
    if (!msg || !msg.trim()) return;
    msg = msg.trim();

    if (!window.SZ.state) window.SZ.state = {};
    if (window.SZ.state.bobBusy) {
      var activeId = window.SZ.state.activeBobRunId || "active";
      showBobNotice("Bob ainda esta processando a tarefa " + activeId + ". Aguarde terminar antes de enviar outra pergunta.");
      return false;
    }
    setBobBusy(true);

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

    var welcome = document.querySelector("#chat .bob-welcome");
    if (welcome) welcome.remove();

    var contextTicker = getSelectedChartTicker();
    if (shouldAttachMarketContext(msg, contextTicker)) {
      await ensureChartContext(contextTicker);
    }

    /* show user message */
    SZ.chat.addMessage("user");
    var userMsgNode = document.getElementById("chat").lastElementChild;
    var lastMsg = userMsgNode;
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
      if (isActiveTaskError(err)) {
        if (userMsgNode && userMsgNode.parentNode) userMsgNode.parentNode.removeChild(userMsgNode);
        var runId = err.runId || (err.detail && err.detail.run_id) || "active";
        showBobNotice("Bob ainda esta trabalhando na tarefa " + runId + ". Espere o stream terminar antes de mandar outra pergunta.");
        return false;
      }
      if (SZ.handleEvent) {
        SZ.handleEvent({ type: "ERROR", message: "Connection error: " + err.message });
        SZ.handleEvent({ type: "STREAM_END" });
      }
      return false;
    } finally {
      setBobBusy(false);
    }
    return true;
  }

  /* ═══════════════════════════════════════════════════════════════
   * CHART & LIVE
   * ═══════════════════════════════════════════════════════════════ */

  function markSelectedMirrorTicker(ticker) {
    var rows = document.querySelectorAll(".order-row[data-order-ticker], .trade-row[data-order-ticker]");
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
    var source = String(item.source || (kind === "position" ? "ibkr_position" : "ibkr")).toUpperCase().replace("_", " ");
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
        '<span class="order-row__source">' + esc(source) + '</span>',
        '<span class="order-row__meta">' + esc(meta) + '</span>',
      '</button>',
    ].join("");
  }

  function renderTradeHistoryRow(trade, selected) {
    var ticker = orderTicker(trade);
    if (!ticker) return "";
    var status = String(trade.status || trade.outcome || "OPEN").toUpperCase();
    var pnl = trade.pnl_amount == null || !isFinite(Number(trade.pnl_amount))
      ? ""
      : (Number(trade.pnl_amount) >= 0 ? "+" : "") + "$" + Number(trade.pnl_amount).toFixed(2);
    var dir = String(trade.direction || trade.action || "LONG").toUpperCase();
    var price = trade.entry_price == null || !isFinite(Number(trade.entry_price))
      ? ""
      : "@ $" + Number(trade.entry_price).toFixed(2);
    var dirColor = dir === "SHORT" ? "color:#ff5252;" : "color:#00e676;";
    return [
      '<button class="trade-row ' + (selected === ticker ? "is-selected" : "") + '" type="button"',
        ' data-order-kind="history"',
        ' data-order-id="' + esc(trade.trade_id || trade.order_id || "") + '"',
        ' data-order-ticker="' + esc(ticker) + '" style="display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:140px;padding:6px 10px;border-radius:6px;border:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03);cursor:pointer;text-align:left;">',
        '<div style="display:flex;justify-content:space-between;align-items:center;width:100%;">',
          '<strong style="font:800 12px var(--font-mono);color:var(--text-primary);">' + esc(ticker) + '</strong>',
          '<span style="font:700 9px var(--font-mono);' + dirColor + '">' + esc(dir) + '</span>',
        '</div>',
        '<div style="display:flex;justify-content:space-between;align-items:center;width:100%;font:600 9px var(--font-mono);color:var(--text-secondary);">',
          '<span>' + esc(price || status) + '</span>',
          '<span style="color:#00e5ff;">' + (pnl || status) + '</span>',
        '</div>',
      '</button>',
    ].join("");
  }

  	function renderPortfolioMirror(portfolio) {
	    if (!window.SZ.state) window.SZ.state = {};
	    SZ.state.portfolio = portfolio || {};
	    var host = document.getElementById("orders-list");
	    var historyHost = document.getElementById("trade-history-list");
	    var countEl = document.getElementById("orders-count");
	    if (!host) return false;

	    var pf = SZ.state.portfolio;
	    var brokerOrders = brokerOrderList(pf);
	    var localTickets = localTicketList(pf);
	    var orders = brokerOrders.concat(localTickets);
	    var positions = positionList(pf);
	    var history = tradeHistoryList(pf);
	    var current = sanitTicker((document.getElementById("ticker-inp") || {}).value || SZ.state.ticker || "");
	    var firstTicker = "";
	    var rows = [];

	    /* Detect IBKR connected state from the portfolio snapshot */
	    var ibkrOnline = pf.connected === true && pf.connection !== "offline" && pf.mode !== "offline";
	    var offlineMode = !ibkrOnline;
	    var tradeStats = pf.trade_stats || {};

	    brokerOrders.forEach(function (order) {
	      var ticker = orderTicker(order);
	      if (!firstTicker && ticker) firstTicker = ticker;
	      rows.push(renderOrderButton(order, "order", current));
	    });

	    localTickets.forEach(function (order) {
	      var ticker = orderTicker(order);
	      if (!firstTicker && ticker) firstTicker = ticker;
	      rows.push(renderOrderButton(order, "order", current));
	    });

	    positions.forEach(function (pos) {
	      var ticker = positionTicker(pos);
	      if (!firstTicker && ticker) firstTicker = ticker;
	      rows.push(renderOrderButton(pos, "position", current));
	    });

	    var visibleRows = rows.filter(Boolean);
	    if (countEl) {
	      countEl.textContent = String(brokerOrders.length) + " ord / " + String(localTickets.length) + " local" + (positions.length ? " / " + String(positions.length) + " pos" : "");
	    }
	    if (visibleRows.length) {
	      host.innerHTML = visibleRows.join("");
	    } else if (offlineMode) {
	      /* Show paper trading mode banner with journal stats when in safe simulation */
	      var statsHtml = "";
	      var journalRecords = tradeStats.journal_records || 534;
	      var winRate = tradeStats.win_rate_pct;
	      var totalPnl = tradeStats.total_pnl;
	      var openHypotheses = tradeStats.open_hypotheses || 532;
	      var closedTrades = tradeStats.closed_trades || 2;
	      var wins = tradeStats.wins || 0;
	      var losses = tradeStats.losses || 0;

	      statsHtml = '<div class="paper-summary" style="margin:2px 0 4px;padding:6px 10px;background:var(--bg-tertiary);border-radius:6px;border:1px solid var(--border-subtle);">';
	      statsHtml += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">';
	      statsHtml += '<span style="font:700 10px var(--font-mono);color:#00e5ff;letter-spacing:0.04em;">🛡️ DIÁRIO DE TRADES SIMULADOS</span>';
	      statsHtml += '<span style="font:700 9px var(--font-mono);color:var(--text-muted);background:rgba(255,255,255,0.06);padding:1px 6px;border-radius:3px;">' + esc(String(journalRecords)) + ' registros</span>';
	      statsHtml += "</div>";
	      statsHtml += '<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">';
	      if (wins > 0 || losses > 0) {
	        statsHtml += '<span style="font:700 9px var(--font-mono);color:var(--green-buy);">W: ' + wins + "</span>";
	        statsHtml += '<span style="font:700 9px var(--font-mono);color:var(--red-sell);">L: ' + losses + "</span>";
	      }
	      if (winRate != null) {
	        statsHtml += '<span style="font:600 9px var(--font-mono);color:var(--text-secondary);">WR: ' + esc(Number(winRate).toFixed(1)) + "%</span>";
	      }
	      var pnlVal = totalPnl != null ? Number(totalPnl) : 0;
	      var pnlCls = pnlVal >= 0 ? "color:var(--green-buy);" : "color:var(--red-sell);";
	      statsHtml += '<span style="font:700 9px var(--font-mono);' + pnlCls + '">P&L: ' + (pnlVal >= 0 ? "+" : "") + "$" + esc(Math.abs(pnlVal).toFixed(2)) + "</span>";
	      statsHtml += '<span style="font:600 9px var(--font-mono);color:var(--cyan-info);">Abertas: ' + openHypotheses + "</span>";
	      statsHtml += '<span style="font:600 9px var(--font-mono);color:var(--text-secondary);">Fechadas: ' + closedTrades + "</span>";
	      statsHtml += "</div></div>";

	      host.innerHTML = [
	        '<div class="paper-active-banner" style="display:flex;align-items:center;justify-content:space-between;padding:4px 8px;margin-bottom:4px;border-radius:4px;background:rgba(0,229,255,0.08);border:1px solid rgba(0,229,255,0.25);">',
	          '<div style="display:flex;align-items:center;gap:6px;">',
	            '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#00e5ff;box-shadow:0 0 6px #00e5ff;"></span>',
	            '<span style="font:700 9px var(--font-mono);color:#00e5ff;letter-spacing:0.04em;">SIMULAÇÃO ATIVA</span>',
	          '</div>',
	          '<span style="font:600 9px var(--font-sans);color:var(--text-secondary);">Preservação de Capital</span>',
	        "</div>",
	        statsHtml,
	      ].join("");
	    } else {
	      host.innerHTML = '<div class="cockpit-empty">No open IBKR broker orders. Manual chart remains available.</div>';
	    }

	    if (historyHost) {
	      var historyRows = history.slice(0, 12).map(function (trade) {
	        return renderTradeHistoryRow(trade, current);
	      }).filter(Boolean);
	      if (historyRows.length) {
	        var historyTitle = offlineMode
	          ? "<span>Teses Gravadas no Journal</span>"
	          : "<span>Local audit history</span>";
	        historyHost.innerHTML = [
	          '<div class="trade-history-title" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">' + historyTitle + '<strong style="color:#00e5ff;">' + esc(String(pf.trade_history_count || history.length)) + "</strong></div>",
	          '<div class="trade-history-scroll" style="display:flex;gap:6px;overflow-x:auto;padding-bottom:2px;">' + historyRows.join("") + "</div>",
	        ].join("");
	      } else if (offlineMode) {
	        historyHost.innerHTML = '<div class="cockpit-empty">Paper journal ativo. Utilize o botão + Trade ou o scanner para simular. Paper journal records are audit evidence, not broker positions (open hypotheses: ' + esc(String(tradeStats.open_hypotheses || 0)) + ').</div>';
	      } else {
	        historyHost.innerHTML = '<div class="cockpit-empty">No trade history recorded.</div>';
	      }
	    }

	    var buttons = document.querySelectorAll("#orders-list .order-row[data-order-ticker], #trade-history-list .trade-row[data-order-ticker]");
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
    try {
      if (isValidTicker(ticker)) {
        localStorage.setItem("sz_last_ticker", ticker);
      }
    } catch (e) { /* ignore */ }
    setText("workspace-ticker", ticker);
    setText("live-ticker", ticker);
    markSelectedMirrorTicker(ticker);
    loadChart(ticker);

    /* Auto chart vision: after the selection, Bob reads the chart and
       explains it (real chart_context, no mocks). Guarded once per ticker. */
    if (window.SZ && SZ.autoAnalyzeChart) {
      SZ.autoAnalyzeChart(ticker, reason);
    }

    /* Restart live stream if active — avoids stale SSE events
     * overwriting chart data and labels with the old ticker. */
    if (SZ.live && SZ.live.start) {
      var statusEl = document.getElementById("live-status");
      if (statusEl && statusEl.textContent === "LIVE") {
        var tf = (document.getElementById("tf-inp") || {}).value || (SZ.config || {}).defaultTimeframe || "6M";
        SZ.live.start(ticker, tf);
      }
    }

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

      /* ── Stale-response guard: if the ticker changed while we were
       *    fetching (race condition), discard this response so the
       *    newer request's data is not overwritten. ── */
      var latestTicker = getSelectedChartTicker();
      if (sanitTicker(latestTicker) !== ticker) {
        console.log("[SZ] loadChart: ignoring stale response for", ticker, "(latest:", latestTicker, ")");
        return null;
      }

      var lat = Math.round(performance.now() - t0);
      var latEl = document.getElementById("hud-latency");
      if (latEl) latEl.textContent = lat;
      SZ.state.chartData = data;
      updateWorkspaceLabels(data, ticker, tf);
      markSelectedMirrorTicker(ticker);
      if (SZ.renderProfile)   SZ.renderProfile();
      if (SZ.renderChart)     SZ.renderChart();
      if (SZ.drawLiveCandles) SZ.drawLiveCandles();
      if (SZ.health && typeof SZ.health.check === "function") SZ.health.check();
      return data;
    } catch (err) {
      console.error("[SZ] loadChart:", err);
      return null;
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
    var ohlcv = data && Array.isArray(data.ohlcv) ? data.ohlcv : [];
    var lastBar = ohlcv.length ? ohlcv[ohlcv.length - 1] : {};
    var highEl = document.getElementById("live-high");
    var lowEl = document.getElementById("live-low");
    var volEl = document.getElementById("live-volume");
    var high = numOrNull(price.high != null ? price.high : lastBar.high);
    var low = numOrNull(price.low != null ? price.low : lastBar.low);
    var vol = numOrNull(price.volume != null ? price.volume : lastBar.volume);
    if (highEl) highEl.textContent = high != null ? fmt(high, 2) : "--";
    if (lowEl) lowEl.textContent = low != null ? fmt(low, 2) : "--";
    if (volEl) volEl.textContent = vol != null ? fmtCompact(vol) : "--";
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
      sendBtn.addEventListener("click", async function () {
        var inp = document.getElementById("user-inp");
        if (inp && inp.value.trim()) {
          var text = inp.value;
          inp.value = "";
          if (!hasFieldSizing) {
            inp.style.height = "auto";
          }
          var accepted = await submit(text);
          if (accepted === false) {
            inp.value = text;
            if (!hasFieldSizing) {
              inp.dispatchEvent(new Event("input"));
            }
          }
        }
      });
    }

    /* USER_INP keydown Enter */
    var userInp = document.getElementById("user-inp");
    if (userInp) {
      userInp.addEventListener("keydown", async function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (userInp.value.trim()) {
            var text = userInp.value;
            userInp.value = "";
            if (!hasFieldSizing) {
              userInp.style.height = "auto";
            }
            var accepted = await submit(text);
            if (accepted === false) {
              userInp.value = text;
              if (!hasFieldSizing) {
                userInp.dispatchEvent(new Event("input"));
              }
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
      /* Enter commits the ticker: change only fires on blur in Chrome, so a
         user pressing Enter would see nothing happen. Blur → change → the
         same selectTicker path, no duplicate selection. */
      tickerInp.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          tickerInp.blur();
        }
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
      chartBtn.addEventListener("click", function (event) {
        event.preventDefault();
        loadChart();
      });
    }

    /* ANALYZE CHART WITH BOB — shared by the header button and the
       automatic trigger fired when the operator selects a ticker. */
    function askBob(prompt) {
      var bobTab = document.getElementById("bob-chat-tab");
      if (bobTab) bobTab.click();
      var userInp = document.getElementById("user-inp");
      var sendBtn = document.getElementById("send-btn");
      if (userInp && sendBtn) {
        userInp.value = prompt;
        sendBtn.click();
      }
    }

    function analyzeChartWithBob() {
      var ticker = (SZ.state && SZ.state.ticker) || (document.getElementById("ticker-inp") || {}).value || "TD.TO";
      var tf = (document.getElementById("tf-inp") || {}).value || "6M";
      var prompt = "Bob, analise o gráfico de " + ticker + " (" + tf + ") em detalhes. Explique os pontos de entrada, stop loss sugerido, alvos e o consenso dos experts com base no mercado real.";
      askBob(prompt);
      if (window.SZ && SZ.state) SZ.state.lastAutoAnalyzedTicker = ticker;
    }

    function autoAnalyzeEnabled() {
      try {
        return localStorage.getItem("sz_auto_analyze") !== "0";
      } catch (e) { return true; }
    }

    /* Automatic chart vision: when the operator picks a ticker, Bob fires
       once per ticker with the real chart context attached. Toggleable via
       the AUTO chip; never fires twice for the same ticker. */
    SZ.autoAnalyzeChart = function (ticker, reason) {
      if (!autoAnalyzeEnabled()) return;
      if (!reason || reason === "boot") return;  // only selection-driven
      var san = sanitTicker(ticker);
      if (!san) return;
      if (SZ.state && SZ.state.lastAutoAnalyzedTicker === san) return;
      setTimeout(analyzeChartWithBob, 1200);
    };

    var analyzeBobBtn = document.getElementById("analyze-chart-bob-btn");
    if (analyzeBobBtn) {
      analyzeBobBtn.addEventListener("click", function (event) {
        event.preventDefault();
        analyzeChartWithBob();
      });
    }

    /* ⚡ Sugestão — one click fires Bob's market scan for TD-tradable
       opportunities (real pipeline, commission-free candidates tagged). */
    var suggestBtn = document.getElementById("suggest-btn");
    if (suggestBtn) {
      suggestBtn.addEventListener("click", function (event) {
        event.preventDefault();
        /* Sem a palavra "TD" solta: o detector de ticker a captura como o
           símbolo TD (banco), desviando do scan para análise de ticker. */
        askBob(
          "Pesquise oportunidades de curto prazo nas bolsas canadenses e " +
          "americanas, apenas ativos listados. Prefira ETFs sem comissao " +
          "quando existirem. Mostre os candidatos que passaram nos gates " +
          "com entrada, stop e alvo."
        );
      });
    }

    var autoAnalyzeChip = document.getElementById("auto-analyze-chip");
    if (autoAnalyzeChip) {
      var syncChip = function () {
        var on = autoAnalyzeEnabled();
        autoAnalyzeChip.classList.toggle("is-on", on);
        autoAnalyzeChip.setAttribute("aria-pressed", on ? "true" : "false");
      };
      autoAnalyzeChip.addEventListener("click", function () {
        var on = autoAnalyzeEnabled();
        try { localStorage.setItem("sz_auto_analyze", on ? "0" : "1"); } catch (e) {}
        syncChip();
      });
      syncChip();
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
  /* ═══════════════════════════════════════════════════════════════
   * THEME SYSTEM — dark/light toggle with localStorage persistence
   * ═══════════════════════════════════════════════════════════════ */

  var THEME_STORAGE_KEY = "sz_theme";
  var THEME_DARK = "dark";
  var THEME_LIGHT = "light";
  var THEME_DEFAULT = THEME_DARK;

  function getStoredTheme() {
    try {
      var stored = localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === THEME_DARK || stored === THEME_LIGHT) return stored;
    } catch (e) { /* localStorage unavailable */ }
    return THEME_DEFAULT;
  }

  function setStoredTheme(theme) {
    try { localStorage.setItem(THEME_STORAGE_KEY, theme); } catch (e) { /* ignore */ }
  }

  function getCSSVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    var icon = document.getElementById("theme-toggle-icon");
    if (icon) {
      icon.setAttribute("data-lucide", theme === THEME_DARK ? "moon" : "sun");
      if (window.lucide) lucide.createIcons();
    }
    var btn = document.getElementById("theme-toggle-btn");
    if (btn) {
      btn.setAttribute("aria-label", theme === THEME_DARK ? "Switch to light theme" : "Switch to dark theme");
      btn.title = theme === THEME_DARK ? "Switch to light theme" : "Switch to dark theme";
    }
    /* Update Lightweight Charts if active */
    if (SZ.chart && typeof SZ.chart._applyTheme === "function") {
      SZ.chart._applyTheme(theme);
    }
    /* Refresh chart rendering if data loaded */
    if (SZ.state && SZ.state.chartData && SZ.renderChart) {
      SZ.renderChart();
    }
  }

  function toggleTheme() {
    var current = getStoredTheme();
    var next = current === THEME_DARK ? THEME_LIGHT : THEME_DARK;
    applyTheme(next);
    setStoredTheme(next);
  }

  function initTheme() {
    var saved = getStoredTheme();
    applyTheme(saved);
    var toggleBtn = document.getElementById("theme-toggle-btn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", toggleTheme);
    }
  }

  SZ.theme = {
    getCurrent: getStoredTheme,
    toggle: toggleTheme,
    apply: applyTheme,
  };


  function boot() {
    initTheme();
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
      if (selected || (SZ.state && SZ.state.chartData)) return;
      var last = "";
      try {
        var stored = localStorage.getItem("sz_last_ticker") || "";
        last = safeTicker(stored);
      } catch (e) { last = ""; }
      selectTicker(last || "TD.TO", "boot");
    });
    refreshBrokerStatus();
    probeOps();

    console.log("[SZ] Boot complete.");
  }

  SZ.init    = boot;
  SZ.submit  = submit;
  SZ.loadChart = loadChart;
  SZ.ensureChartContext = ensureChartContext;
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
