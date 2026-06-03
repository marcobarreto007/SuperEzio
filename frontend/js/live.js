/**
 * live.js — SSE live stream management
 * startLiveStream(ticker, tf) creates EventSource to SZ.api.sseURL().
 * Handles: snapshot, candle, heartbeat, error.
 * mergeLiveCandle(payload) updates state.chartData.ohlcv (up to 500, dedup by time).
 * updateLiveMetrics() updates DOM: live-ticker, live-price, live-change.
 * stopLiveStream() closes EventSource.
 * Exports: SZ.live = { start, stop }
 */
(function () {
  "use strict";

  var MAX_POINTS = 500;
  var RETRY_MS   = 4000;
  var _es        = null;   // active EventSource
  var _ticker    = "";
  var _tf        = "";
  var _retryTimer = null;

  /* ── helpers ── */
  function dedupMerge(ohlcv, candle) {
    if (!candle || !candle.time) return ohlcv;
    /* replace existing candle at same time or append */
    for (var i = ohlcv.length - 1; i >= 0; i--) {
      if (ohlcv[i].time === candle.time) {
        ohlcv[i] = candle;
        return ohlcv;
      }
    }
    ohlcv.push(candle);
    return ohlcv;
  }

  function trimToMax(arr) {
    if (arr.length > MAX_POINTS) arr.splice(0, arr.length - MAX_POINTS);
    return arr;
  }

  function mergeIndicators(existing, incoming) {
    if (!incoming) return existing || {};
    if (!existing) return incoming;
    /* shallow-merge each key (arrays are replaced) */
    for (var k in incoming) {
      if (incoming.hasOwnProperty(k)) existing[k] = incoming[k];
    }
    return existing;
  }

  /* ── update DOM metrics ── */
  function updateLiveMetrics() {
    var cd  = SZ.state && SZ.state.chartData;
    var ohlcv = cd && cd.ohlcv;
    if (!ohlcv || !ohlcv.length) return;

    var last = ohlcv[ohlcv.length - 1];

    var elTicker  = document.getElementById("live-ticker");
    var elSideTicker = document.getElementById("side-ticker");
    var elWorkspaceTicker = document.getElementById("workspace-ticker");
    var elPrice   = document.getElementById("live-price");
    var elChange  = document.getElementById("live-change");
    var elTs      = document.getElementById("live-ts");

    if (elTicker)  elTicker.textContent = _ticker.toUpperCase();
    if (elSideTicker) elSideTicker.textContent = _ticker.toUpperCase();
    if (elWorkspaceTicker) elWorkspaceTicker.textContent = _ticker.toUpperCase();
    if (elPrice)   elPrice.textContent  = last.close != null ? last.close.toFixed(2) : "";

    if (elChange && ohlcv.length > 1) {
      var prev = ohlcv[ohlcv.length - 2].close;
      if (prev && last.close) {
        var pct = ((last.close - prev) / prev) * 100;
        elChange.textContent  = (pct >= 0 ? "+" : "") + pct.toFixed(2) + "%";
        elChange.style.color  = pct >= 0 ? "#00c853" : "#ff1744";
      }
    }

    if (elTs) {
      var now = new Date();
      elTs.textContent = now.toLocaleTimeString();
    }
  }

  /* ── merge a single candle into state ── */
  function mergeLiveCandle(payload) {
    var cd = SZ.state && SZ.state.chartData;
    if (!cd) return;
    cd.ohlcv = dedupMerge(cd.ohlcv || [], payload);
    trimToMax(cd.ohlcv);
    if (payload.indicators) {
      cd.indicators = mergeIndicators(cd.indicators, payload.indicators);
    }
  }

  /* ── snapshot handler ── */
  function handleSnapshot(data) {
    if (!SZ.state) SZ.state = {};
    if (data.ohlcv) {
      SZ.state.chartData = SZ.state.chartData || {};
      SZ.state.chartData.ohlcv = data.ohlcv;
      trimToMax(SZ.state.chartData.ohlcv);
    }
    if (data.indicators) {
      SZ.state.chartData = SZ.state.chartData || {};
      SZ.state.chartData.indicators = data.indicators;
    }
    if (data.meta) {
      SZ.state.chartData = SZ.state.chartData || {};
      SZ.state.chartData.meta = data.meta;
    }
    /* trigger renders */
    if (SZ.renderProfile)   SZ.renderProfile();
    if (SZ.renderChart)     SZ.renderChart();
    updateLiveMetrics();
  }

  /* ── single candle handler ── */
  function handleCandle(data) {
    mergeLiveCandle(data);
    if (SZ.drawLiveCandles) SZ.drawLiveCandles();
    updateLiveMetrics();
  }

  /* ── heartbeat handler ── */
  function handleHeartbeat() {
    var elTs = document.getElementById("live-ts");
    if (elTs) elTs.textContent = new Date().toLocaleTimeString();
  }

  /* ── show retry indicator ── */
  function showRetry(msg) {
    var el = document.getElementById("live-status");
    if (el) {
      el.textContent = msg || "Reconnecting...";
      el.style.color = "#ff9800";
    }
  }

  function showConnected() {
    var el = document.getElementById("live-status");
    if (el) {
      el.textContent = "LIVE";
      el.style.color = "#00c853";
    }
  }

  /* ── start ── */
  function startLiveStream(ticker, tf) {
    stopLiveStream();
    _ticker = (ticker || "").toUpperCase();
    _tf     = tf || "1d";

    if (!SZ.api || !SZ.api.sseURL) {
      console.warn("[SZ.live] SZ.api.sseURL not available");
      return;
    }

    var url = SZ.api.sseURL(_ticker, _tf);
    try {
      _es = new EventSource(url);
    } catch (e) {
      console.error("[SZ.live] EventSource failed:", e);
      return;
    }

    _es.addEventListener("snapshot", function (e) {
      try { handleSnapshot(JSON.parse(e.data)); } catch (err) { console.error("[SZ.live] snapshot parse error:", err); }
    });

    _es.addEventListener("candle", function (e) {
      try { handleCandle(JSON.parse(e.data)); } catch (err) { console.error("[SZ.live] candle parse error:", err); }
    });

    _es.addEventListener("heartbeat", function () {
      handleHeartbeat();
    });

    _es.onerror = function () {
      showRetry("Reconnecting...");
      /* EventSource auto-reconnects, but we set a visual fallback */
      clearTimeout(_retryTimer);
      _retryTimer = setTimeout(function () {
        if (_es && _es.readyState === EventSource.CLOSED) {
          showRetry("Disconnected");
        }
      }, RETRY_MS + 2000);
    };

    _es.onopen = function () {
      showConnected();
    };

    showConnected();
  }

  /* ── stop ── */
  function stopLiveStream() {
    if (_es) {
      _es.close();
      _es = null;
    }
    clearTimeout(_retryTimer);
    _retryTimer = null;
    var el = document.getElementById("live-status");
    if (el) {
      el.textContent = "SNAPSHOT";
      el.style.color = "#5a6e62";
    }
  }

  /* ── export ── */
  if (!window.SZ) window.SZ = {};
  window.SZ.live = {
    start: startLiveStream,
    stop:  stopLiveStream
  };
})();
