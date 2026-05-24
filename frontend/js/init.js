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
      if (s[i] != null && isFinite(s[i])) return s[i];
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
    if (cd.meta) {
      if (cd.meta.name)     lines.push("Asset: " + cd.meta.name);
      if (cd.meta.sector)   lines.push("Sector: " + cd.meta.sector);
      if (cd.meta.exchange) lines.push("Exchange: " + cd.meta.exchange);
    }
    var ohlcv = cd.ohlcv || [];
    if (ohlcv.length) {
      var last = ohlcv[ohlcv.length - 1];
      lines.push("Last close: " + fmt(last && last.close));
      lines.push("Data points: " + ohlcv.length);
    }
    var ind = cd.indicators || {};
    if (ind.sma_20)  lines.push("SMA20: "  + fmt(lastVal(ind.sma_20)));
    if (ind.sma_50)  lines.push("SMA50: "  + fmt(lastVal(ind.sma_50)));
    if (ind.ema_20)  lines.push("EMA20: "  + fmt(lastVal(ind.ema_20)));
    if (ind.rsi)     lines.push("RSI: "     + fmt(lastVal(ind.rsi)));
    if (ind.macd) {
      var m = ind.macd;
      if (m.macd)       lines.push("MACD: "     + fmt(lastVal(m.macd)));
      if (m.signal)     lines.push("MACD Sig: " + fmt(lastVal(m.signal)));
      if (m.histogram)  lines.push("MACD Hist: " + fmt(lastVal(m.histogram)));
    }
    lines.push("=== END CHART CONTEXT ===");
    return lines.join("\n");
  }

  function buildPortfolioContext() {
    var pf = SZ.state && SZ.state.portfolio;
    if (!pf) return "";
    var keys = Object.keys(pf);
    if (!keys.length) return "";
    var lines = ["=== PORTFOLIO ==="];
    keys.forEach(function (k) {
      var p = pf[k];
      if (p && p.shares) lines.push(k + ": " + p.shares + " shares");
    });
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
      var ticker = sanitTicker((document.getElementById("ticker-inp") || {}).value || "AAPL") || "AAPL";
      var tf = (document.getElementById("tf-inp") || {}).value || "6M";
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

  /* ═══════════════════════════════════════════════════════════════
   * TASK SUBMISSION
   * ═══════════════════════════════════════════════════════════════ */

  function buildEnvelope(msg) {
    var ticker = sanitTicker(
      (document.getElementById("ticker-inp") || {}).value || ""
    );
    var tf = (document.getElementById("tf-inp") || {}).value || "6M";
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

  async function loadChart() {
    var ticker = sanitTicker(
      (document.getElementById("ticker-inp") || {}).value || ""
    );
    var tf = (document.getElementById("tf-inp") || {}).value || "6M";
    if (!ticker) return;

    var t0 = performance.now();
    try {
      var data = await SZ.api.fetchChartData(ticker, tf);
      var lat = Math.round(performance.now() - t0);
      var latEl = document.getElementById("hud-latency");
      if (latEl) latEl.textContent = lat;
      SZ.state.chartData = data;
      updateWorkspaceLabels(data, ticker, tf);
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
    var ticker = sanitTicker(
      (document.getElementById("ticker-inp") || {}).value || ""
    );
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
    /* SEND button */
    var sendBtn = document.getElementById("send-btn");
    if (sendBtn) {
      sendBtn.addEventListener("click", function () {
        var inp = document.getElementById("user-inp");
        if (inp && inp.value.trim()) {
          submit(inp.value);
          inp.value = "";
          inp.style.height = "auto";
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
            userInp.style.height = "auto";
          }
        }
      });
      userInp.addEventListener("input", function () {
        userInp.style.height = "auto";
        userInp.style.height = Math.min(userInp.scrollHeight, 160) + "px";
      });
    }

    /* TICKER / TF change */
    var tickerInp = document.getElementById("ticker-inp");
    if (tickerInp) {
      tickerInp.addEventListener("change", loadChart);
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

    loadChart();
    probeOps();

    console.log("[SZ] Boot complete.");
  }

  SZ.init    = boot;
  SZ.submit  = submit;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
