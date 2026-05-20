/**
 * render-chart.js — Inline chart card with ALL indicators
 * Canvas rendering with dark theme. Draws: price line, SMA20, SMA50,
 * EMA20, Bollinger Bands, MACD histogram.
 * Exports: SZ.renderChart(ceo)
 */
(function () {
  "use strict";

  /* ── colour palette ─────────────────────────────────────────── */
  var BG       = "#0d1210";
  var GRID     = "#1a2a1e";
  var MUTED    = "#5a6e62";
  var WHITE    = "#e8efe8";
  var BLUE     = "#448aff";
  var CYAN     = "#00e5ff";
  var PURPLE   = "#b388ff";
  var BB_FILL  = "rgba(100,160,130,0.08)";
  var BB_LINE  = "rgba(100,160,130,0.35)";
  var MACD_UP  = "#00c853";
  var MACD_DN  = "#ff1744";

  var STEPS = [
    "orchestrator","data","f51","pennylab","experts",
    "neural","sdca","rag","ceo","explanation"
  ];

  /* ── helpers ─────────────────────────────────────────────────── */
  function lastOf(arr) {
    return arr && arr.length ? arr[arr.length - 1] : null;
  }
  function minMax(arr) {
    var lo = Infinity, hi = -Infinity;
    for (var i = 0; i < arr.length; i++) {
      if (arr[i] != null && isFinite(arr[i])) {
        if (arr[i] < lo) lo = arr[i];
        if (arr[i] > hi) hi = arr[i];
      }
    }
    return { lo: lo, hi: hi };
  }
  function niceRange(lo, hi, ticks) {
    var range = hi - lo || 1;
    var step  = range / ticks;
    var mag   = Math.pow(10, Math.floor(Math.log10(step)));
    var res   = step / mag;
    if (res <= 1.5)      step = 1 * mag;
    else if (res <= 3)   step = 2 * mag;
    else if (res <= 7)   step = 5 * mag;
    else                 step = 10 * mag;
    return {
      lo: Math.floor(lo / step) * step,
      hi: Math.ceil(hi / step) * step,
      step: step
    };
  }

  /* ── main renderer ──────────────────────────────────────────── */
  function renderChart(ceo) {
    var container = document.getElementById("live-canvas");
    if (!container) return;
    var parent = container.parentElement;

    var cd = SZ.state && SZ.state.chartData;
    if (!cd || !cd.indicators) { return; }

    var ind = cd.indicators;
    var ohlcv = cd.ohlcv || [];
    if (!ohlcv.length) return;

    /* ── figure out dimensions ── */
    var W = (parent ? parent.clientWidth : container.clientWidth)  || 800;
    var H = (parent ? parent.clientHeight : container.clientHeight) || 420;
    var dpr = window.devicePixelRatio || 1;

    /* reserve bottom 20 % for MACD */
    var PRICE_H = H * 0.75;
    var MACD_Y  = PRICE_H + H * 0.05;
    var MACD_H  = H * 0.20;
    var PAD_L   = 58, PAD_R = 12, PAD_T = 18, PAD_B = 22;
    var PW = W - PAD_L - PAD_R;   // plot width
    var PH = PRICE_H - PAD_T - PAD_B;

    /* ── use the live-canvas directly ── */
    var canvas = container;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width  = W + "px";
    canvas.style.height = H + "px";
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);

    /* ── extract price series ── */
    var closes = ohlcv.map(function (b) { return b.close; });
    var times  = ohlcv.map(function (b) { return b.time; });
    var N = closes.length;

    /* helper: index → x */
    function xOf(i) { return PAD_L + (i / (N - 1)) * PW; }

    /* ── price range ── */
    var pRange = minMax(closes);
    /* expand for Bollinger if present */
    var bbUp = ind.bollinger_upper || [];
    var bbLo = ind.bollinger_lower || [];
    if (bbUp.length) { var r1 = minMax(bbUp); pRange.lo = Math.min(pRange.lo, r1.lo); pRange.hi = Math.max(pRange.hi, r1.hi); }
    if (bbLo.length) { var r2 = minMax(bbLo); pRange.lo = Math.min(pRange.lo, r2.lo); pRange.hi = Math.max(pRange.hi, r2.hi); }
    var nice = niceRange(pRange.lo, pRange.hi, 5);
    function yOfPrice(v) { return PAD_T + PH - ((v - nice.lo) / (nice.hi - nice.lo)) * PH; }

    /* ── clear ── */
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, W, H);

    /* ── grid lines ── */
    ctx.strokeStyle = GRID;
    ctx.lineWidth = 0.5;
    for (var v = nice.lo; v <= nice.hi + nice.step * 0.5; v += nice.step) {
      var gy = yOfPrice(v);
      ctx.beginPath(); ctx.moveTo(PAD_L, gy); ctx.lineTo(W - PAD_R, gy); ctx.stroke();
      /* y-axis label */
      ctx.fillStyle = MUTED;
      ctx.font = "10px monospace";
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(2), PAD_L - 6, gy + 3);
    }
    /* vertical grid (time) */
    var timeStep = Math.max(1, Math.floor(N / 6));
    for (var t = 0; t < N; t += timeStep) {
      var gx = xOf(t);
      ctx.strokeStyle = GRID;
      ctx.beginPath(); ctx.moveTo(gx, PAD_T); ctx.lineTo(gx, PRICE_H - PAD_B); ctx.stroke();
      ctx.fillStyle = MUTED;
      ctx.textAlign = "center";
      ctx.font = "10px monospace";
      var lbl = times[t];
      if (lbl) {
        var d = new Date(lbl);
        if (isFinite(d.getTime())) lbl = d.toLocaleDateString("en-US", { month:"short", day:"numeric" });
      }
      ctx.fillText(lbl || "", gx, PRICE_H - PAD_B + 14);
    }

    /* ── Bollinger Bands (fill first so lines overlay) ── */
    if (bbUp.length && bbLo.length) {
      var len = Math.min(bbUp.length, bbLo.length, N);
      ctx.beginPath();
      for (var i = 0; i < len; i++) ctx.lineTo(xOf(i), yOfPrice(bbUp[i]));
      for (var i2 = len - 1; i2 >= 0; i2--) ctx.lineTo(xOf(i2), yOfPrice(bbLo[i2]));
      ctx.closePath();
      ctx.fillStyle = BB_FILL;
      ctx.fill();
      /* upper line */
      ctx.strokeStyle = BB_LINE; ctx.lineWidth = 1; ctx.setLineDash([]);
      ctx.beginPath();
      for (var i3 = 0; i3 < len; i3++) { if (i3 === 0) ctx.moveTo(xOf(i3), yOfPrice(bbUp[i3])); else ctx.lineTo(xOf(i3), yOfPrice(bbUp[i3])); }
      ctx.stroke();
      /* lower line */
      ctx.beginPath();
      for (var i4 = 0; i4 < len; i4++) { if (i4 === 0) ctx.moveTo(xOf(i4), yOfPrice(bbLo[i4])); else ctx.lineTo(xOf(i4), yOfPrice(bbLo[i4])); }
      ctx.stroke();
    }

    /* ── line helper ── */
    function drawSeries(arr, color, dash) {
      if (!arr || !arr.length) return;
      var l = Math.min(arr.length, N);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.setLineDash(dash || []);
      ctx.beginPath();
      for (var j = 0; j < l; j++) {
        var px = xOf(j), py = yOfPrice(arr[j]);
        if (j === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    /* ── indicator lines ── */
    drawSeries(ind.sma_20,  BLUE,  [6, 3]);    // SMA20 — blue dashed
    drawSeries(ind.sma_50,  CYAN,  [6, 3]);    // SMA50 — cyan dashed
    drawSeries(ind.ema_20,  PURPLE,[2, 3]);    // EMA20 — purple dotted

    /* ── price line (white, on top) ── */
    drawSeries(closes, WHITE, []);

    /* ── MACD histogram (bottom 20%) ── */
    var hist = (ind.macd && ind.macd.histogram) || [];
    if (hist.length) {
      var hRange = minMax(hist);
      var hAbs   = Math.max(Math.abs(hRange.lo), Math.abs(hRange.hi)) || 1;
      var hZero  = MACD_Y + MACD_H / 2;
      var barW   = Math.max(1, (PW / hist.length) * 0.7);
      for (var k = 0; k < Math.min(hist.length, N); k++) {
        var bx = xOf(k);
        var val = hist[k];
        var bh  = (val / hAbs) * (MACD_H / 2);
        ctx.fillStyle = val >= 0 ? MACD_UP : MACD_DN;
        if (val >= 0) ctx.fillRect(bx - barW / 2, hZero - bh, barW, bh);
        else          ctx.fillRect(bx - barW / 2, hZero, barW, -bh);
      }
      /* zero line */
      ctx.strokeStyle = MUTED;
      ctx.lineWidth = 0.5;
      ctx.beginPath(); ctx.moveTo(PAD_L, hZero); ctx.lineTo(W - PAD_R, hZero); ctx.stroke();
      /* MACD label */
      ctx.fillStyle = MUTED;
      ctx.font = "9px monospace";
      ctx.textAlign = "left";
      ctx.fillText("MACD", PAD_L, MACD_Y + 10);
    }

    /* ── legend ── */
    ctx.font = "10px monospace";
    var lx = PAD_L + 4, ly = PAD_T + 12;
    ctx.fillStyle = WHITE;  ctx.fillText("Price", lx, ly); lx += 44;
    ctx.fillStyle = BLUE;   ctx.fillText("SMA20", lx, ly); lx += 50;
    ctx.fillStyle = CYAN;   ctx.fillText("SMA50", lx, ly); lx += 50;
    ctx.fillStyle = PURPLE; ctx.fillText("EMA20", lx, ly); lx += 50;
    ctx.fillStyle = BB_LINE; ctx.fillText("BB", lx, ly);
  }

  /* ── export ──────────────────────────────────────────────────── */
  if (!window.SZ) window.SZ = {};
  window.SZ.renderChart = renderChart;
})();
