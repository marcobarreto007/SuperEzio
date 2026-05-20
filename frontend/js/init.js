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

    return {
      jsonrpc: "2.0",
      method:  "message/send",
      id:      "sz-" + Date.now(),
      params: {
        message: {
          role: "user",
          parts: [{ type: "text", text: msg }]
        },
        metadata: {
          ticker:     ticker,
          timeframe:  tf,
          chart_context:     buildChartContext(),
          portfolio_context: buildPortfolioContext()
        }
      }
    };
  }

  async function submit(msg) {
    if (!msg || !msg.trim()) return;
    msg = msg.trim();

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

    try {
      var resp = await SZ.api.submitTask(envelope);

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
          try {
            var ev = JSON.parse(line);
            if (SZ.handleEvent) SZ.handleEvent(ev);
          } catch (parseErr) {
            console.warn("[SZ] NDJSON parse:", parseErr, line);
          }
        }
      }

      if (buffer.trim()) {
        try {
          var ev2 = JSON.parse(buffer.trim());
          if (SZ.handleEvent) SZ.handleEvent(ev2);
        } catch (e) { /* ignore */ }
      }

    } catch (err) {
      console.error("[SZ] submit error:", err);
      if (SZ.handleEvent) {
        SZ.handleEvent({ type: "ERROR", message: "Connection error: " + err.message });
      }
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

    try {
      var data = await SZ.api.fetchChartData(ticker, tf);
      SZ.state.chartData = data;
      if (SZ.renderProfile)   SZ.renderProfile();
      if (SZ.renderChart)     SZ.renderChart();
    } catch (err) {
      console.error("[SZ] loadChart:", err);
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
   * PANEL TABS — toggle the system panel drawer
   * ═══════════════════════════════════════════════════════════════ */

  var activePanel = null;

  function showPanel(name) {
    var drawer = document.getElementById("panel-drawer");
    var content = document.getElementById("panel-content");
    if (!drawer || !content) return;

    if (activePanel === name) {
      drawer.classList.remove("open");
      activePanel = null;
      return;
    }

    activePanel = name;
    drawer.classList.add("open");

    switch (name) {
      case "sysinfo":
        if (SZ.health && SZ.health.showPanel) SZ.health.showPanel();
        break;
      case "metrics":
        if (SZ.metrics && SZ.metrics.showPanel) SZ.metrics.showPanel();
        break;
      case "manifest":
        if (SZ.manifest && SZ.manifest.showPanel) SZ.manifest.showPanel();
        break;
      case "logs":
        if (SZ.neuralLogs && SZ.neuralLogs.showPanel) SZ.neuralLogs.showPanel();
        break;
      case "capabilities":
        if (SZ.capabilities && SZ.capabilities.showPanel) SZ.capabilities.showPanel();
        break;
      case "journal":
        if (SZ.journal && SZ.journal.showPanel) SZ.journal.showPanel();
        break;
      default:
        content.innerHTML = '<div style="color:var(--muted);font-size:12px">Unknown panel.</div>';
    }
  }

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
        var panel = document.getElementById("sdca-lab");
        if (panel) panel.classList.toggle("open");
      });
    }
    var sdcaLabClose = document.getElementById("sdca-lab-close");
    if (sdcaLabClose) {
      sdcaLabClose.addEventListener("click", function () {
        var panel = document.getElementById("sdca-lab");
        if (panel) panel.classList.remove("open");
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

    /* Panel tabs */
    var tabs = document.querySelectorAll("[data-panel]");
    for (var i = 0; i < tabs.length; i++) {
      (function (tab) {
        tab.addEventListener("click", function () {
          showPanel(tab.getAttribute("data-panel"));
        });
      })(tabs[i]);
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
