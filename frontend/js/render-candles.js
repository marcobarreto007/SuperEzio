/**
 * render-candles.js — Live candlestick canvas
 * Dark background. Green (#00c853) for up, red (#ff1744) for down.
 * Grid lines, last price label, timeframe label, retina 2x.
 * Draws up to 140 candles. Exports: SZ.drawLiveCandles()
 */
(function () {
  "use strict";

  /* ── palette ── */
  var BG        = "#0d1210";
  var GRID      = "#1a2a1e";
  var MUTED     = "#5a6e62";
  var WHITE     = "#e8efe8";
  var GREEN     = "#00c853";
  var RED       = "#ff1744";
  var WICK_CLR  = "#3a4e42";
  var MAX_CANDLES = 140;

  /* ── main ── */
  function drawLiveCandles() {
    var container = document.getElementById("live-canvas");
    if (!container) return;
    var parent = container.parentElement;

    var cd = SZ.state && SZ.state.chartData;
    var ohlcv = cd && cd.ohlcv;
    if (!ohlcv || !ohlcv.length) return;

    var candles = ohlcv.slice(-MAX_CANDLES);
    var N = candles.length;
    if (N < 2) return;

    var W = (parent ? parent.clientWidth : container.clientWidth)  || 800;
    var H = (parent ? parent.clientHeight : container.clientHeight) || 360;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);

    var canvas = container;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + "px";
    canvas.style.height = H + "px";
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    /* ── padding ── */
    var PL = 56, PR = 48, PT = 16, PB = 24;
    var PW = W - PL - PR;
    var PH = H - PT - PB;

    /* ── price range from all H/L ── */
    var hi = -Infinity, lo = Infinity;
    for (var i = 0; i < N; i++) {
      if (candles[i].high > hi) hi = candles[i].high;
      if (candles[i].low  < lo) lo = candles[i].low;
    }
    var margin = (hi - lo) * 0.05 || 0.5;
    hi += margin; lo -= margin;
    var range = hi - lo || 1;

    function yOf(v) { return PT + PH - ((v - lo) / range) * PH; }
    function xOf(idx) {
      var gap = PW / N;
      var cw  = gap * 0.7;
      var off = gap * 0.15;
      return PL + idx * gap + off;
    }
    function candleWidth() { return (PW / N) * 0.7; }

    /* ── clear ── */
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, W, H);

    /* ── horizontal grid ── */
    var gridLines = 5;
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 0.5;
    ctx.fillStyle = MUTED;
    ctx.font = "10px monospace";
    ctx.textAlign = "right";
    for (var g = 0; g <= gridLines; g++) {
      var gv = lo + (range / gridLines) * g;
      var gy = yOf(gv);
      ctx.beginPath(); ctx.moveTo(PL, gy); ctx.lineTo(W - PR, gy); ctx.stroke();
      ctx.fillText(gv.toFixed(2), PL - 6, gy + 3);
    }

    /* ── vertical grid (sparse) ── */
    var vStep = Math.max(1, Math.floor(N / 6));
    ctx.textAlign = "center";
    for (var vi = 0; vi < N; vi += vStep) {
      var vx = PL + (vi / N) * PW + (PW / N) * 0.5;
      ctx.strokeStyle = GRID;
      ctx.beginPath(); ctx.moveTo(vx, PT); ctx.lineTo(vx, H - PB); ctx.stroke();
      var tLbl = candles[vi].time;
      if (tLbl) {
        var ts = Number(tLbl);
        var d = new Date(ts < 1000000000000 ? ts * 1000 : ts);
        if (isFinite(d.getTime())) tLbl = d.toLocaleDateString("en-US", { month:"short", day:"numeric" });
      }
      ctx.fillStyle = MUTED;
      ctx.fillText(tLbl || "", vx, H - PB + 14);
    }

    /* ── draw candles ── */
    var cw = candleWidth();
    for (var c = 0; c < N; c++) {
      var bar = candles[c];
      var up  = bar.close >= bar.open;
      var clr = up ? GREEN : RED;
      var cx  = xOf(c);

      /* wick */
      ctx.strokeStyle = clr;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx + cw / 2, yOf(bar.high));
      ctx.lineTo(cx + cw / 2, yOf(bar.low));
      ctx.stroke();

      /* body */
      var yOpen  = yOf(bar.open);
      var yClose = yOf(bar.close);
      var bodyTop    = Math.min(yOpen, yClose);
      var bodyHeight = Math.max(Math.abs(yClose - yOpen), 1);
      ctx.fillStyle = clr;
      ctx.fillRect(cx, bodyTop, cw, bodyHeight);
    }

    /* ── last price label ── */
    var last = candles[N - 1];
    var lastY = yOf(last.close);
    var lastClr = last.close >= last.open ? GREEN : RED;
    ctx.fillStyle = lastClr;
    ctx.font = "bold 11px monospace";
    ctx.textAlign = "left";
    ctx.fillText(last.close.toFixed(2), W - PR + 4, lastY + 4);

    /* horizontal marker at last price */
    ctx.strokeStyle = lastClr;
    ctx.lineWidth = 0.6;
    ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(PL, lastY); ctx.lineTo(W - PR, lastY); ctx.stroke();
    ctx.setLineDash([]);

    /* ── timeframe label ── */
    var tfEl = document.getElementById("tf-inp");
    var tf   = tfEl ? tfEl.value : "";
    if (tf) {
      ctx.fillStyle = MUTED;
      ctx.font = "10px monospace";
      ctx.textAlign = "right";
      ctx.fillText(tf.toUpperCase(), W - PR, PT + 12);
    }
  }

  /* ── export ── */
  if (!window.SZ) window.SZ = {};
  window.SZ.drawLiveCandles = drawLiveCandles;
})();
