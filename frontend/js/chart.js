/**
 * chart.js — GPU-accelerated WebGL chart using Lightweight Charts (TradingView)
 *
 * Replaces the Canvas 2D implementation in render-chart.js / render-candles.js
 * with a WebGL-accelerated chart engine.
 *
 * DESIGN SYSTEM (DATAVIZ METHOD):
 *   Surface: #111820
 *   Categorical: #00e676 (green), #00e5ff (cyan), #ffffff (white)
 *   Bull candle: #00e676, Bear candle: #ef5350
 *   Grid/axes: rgba(255,255,255,0.06), labels in #8b949e
 *
 * METHOD (7 steps):
 *   1. Form: CANDLESTICK (time-series OHLCV) + overlays — correct for price data
 *   2. Color by job: identity (ticker) = cyan/green, polarity (up/down) = green/red,
 *      sequential (volume) = one hue recessive
 *   3. Validate palette: dark mode surface #111820
 *   4. Mark specs: thin wicks (1px), body min 1px, volume bars recessive (< 25% opacity)
 *   5. Hover layer: crosshair + tooltip with OHLCV + indicator values
 *   6. Accessibility: legend for indicators, direct labels on key levels
 *   7. Render and check
 *
 * EXPORTS:
 *   SZ.chart.load(ticker, timeframe)   — primary API
 *   SZ.chart.update(candle)            — real-time SSE merge
 *   SZ.chart.destroy()                 — teardown
 *   SZ.renderChart()                   — backward compat (reads SZ.state.chartData)
 *   SZ.drawLiveCandles()               — backward compat alias
 */
(function () {
  'use strict';

  if (typeof LightweightCharts === 'undefined') {
    console.warn('[SZ.chart] LightweightCharts library not loaded. Chart disabled.');
    return;
  }

  /* ──────────────────────────────────────────────────────────────
   * DESIGN TOKENS
   * ────────────────────────────────────────────────────────────── */

  /* All colors from the SuperEzio design system, mapped per dataviz job:
   *   Surface / chrome  → recessive, non-interfering
   *   Polarity (up/dn)  → bull #00e676, bear #ef5350
   *   Categorical       → identity hues for indicators
   *   Sequential        → one hue for volume (recessive)
   *   Status            → reserved (not used here)
   */
  var C = {
    surface:  '#111820',
    gridLine: 'rgba(255,255,255,0.06)',
    border:   'rgba(255,255,255,0.08)',
    text:     '#8b949e',
    textLight:'#f0f7f2',

    crosshair: 'rgba(255,255,255,0.18)',

    /* Polarity */
    bull: '#00e676',
    bear: '#ef5350',

    /* Volume (sequential — one hue, recessive) */
    volBull: 'rgba(0,230,118,0.22)',
    volBear: 'rgba(239,83,80,0.22)',

    /* Categorical — identity for each indicator */
    sma20: '#00e5ff',
    sma50: '#00e676',
    ema20: '#ffffff',
    bbLine: 'rgba(0,230,118,0.18)',
    bbFill: 'rgba(0,230,118,0.035)',
    vwap:  '#ff9100',

    /* RSI sub-pane */
    rsiLine:   '#00e5ff',
    rsiOb:     'rgba(239,83,80,0.20)',
    rsiOs:     'rgba(0,230,118,0.20)',

    /* MACD sub-pane */
    macdLine:     '#00e5ff',
    macdSignal:   '#ff9100',
    macdHistUp:   'rgba(0,230,118,0.55)',
    macdHistDown: 'rgba(239,83,80,0.55)',
  };

  /* ──────────────────────────────────────────────────────────────
   * STATE
   * ────────────────────────────────────────────────────────────── */

  var mainChart       = null;
  var rsiChart        = null;
  var macdChart       = null;

  var candleSeries    = null;
  var volumeSeries    = null;
  var sma20Series     = null;
  var sma50Series     = null;
  var ema20Series     = null;
  var bbUpperSeries   = null;
  var bbLowerSeries   = null;
  var vwapSeries      = null;

  var rsiLineSeries   = null;
  var rsiObSeries     = null;
  var rsiOsSeries     = null;

  var macdHistSeries  = null;
  var macdLineSeries  = null;
  var macdSignalSeries= null;

  var tooltipEl       = null;
  var legendEl        = null;
  var rsiOverlayEl    = null;
  var macdOverlayEl   = null;

  var resizeRO        = null;
  var chartDataCache  = null;   // last applied data snapshot
  var lastTicker      = '';
  var lastTf          = '';
  var isInitialized   = false;
  var isDestroyed     = false;
  var tooltipTimeout  = null;

  /* ──────────────────────────────────────────────────────────────
   * HELPERS
   * ────────────────────────────────────────────────────────────── */

  /** Convert domain time to LW Unix-seconds timestamp */
  function toLWTime(time) {
    if (time == null) return null;
    var n = Number(time);
    if (!isFinite(n)) return time;
    return n < 1000000000000 ? n : Math.floor(n / 1000);
  }

  /** Build OHLCV data for LW candlestick series */
  function buildOHLCV(ohlcv) {
    var out = [];
    for (var i = 0; i < ohlcv.length; i++) {
      var b = ohlcv[i];
      if (!b || b.time == null) continue;
      out.push({
        time: toLWTime(b.time),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      });
    }
    return out;
  }

  /** Build volume histogram data */
  function buildVolume(ohlcv) {
    var out = [];
    for (var i = 0; i < ohlcv.length; i++) {
      var b = ohlcv[i];
      if (!b || b.time == null || b.volume == null) continue;
      /* Backend can return {time, value} objects or plain numbers for volume */
      var vol = (typeof b.volume === 'object' && b.volume !== null) ? b.volume.value : b.volume;
      if (vol == null || !isFinite(vol)) continue;
      out.push({
        time: toLWTime(b.time),
        value: vol,
        color: b.close >= b.open ? C.volBull : C.volBear,
      });
    }
    return out;
  }

  /** Build line data from a parallel indicator array */
  function buildLineData(arr, ohlcv) {
    if (!arr || !ohlcv) return [];
    var out = [];
    var len = Math.min(arr.length, ohlcv.length);
    for (var i = 0; i < len; i++) {
      var raw = arr[i];
      if (raw == null) continue;
      /* Backend can return {time, value} objects or plain numbers */
      var val = (typeof raw === 'object' && raw !== null) ? raw.value : raw;
      if (val != null && isFinite(val) && ohlcv[i] && ohlcv[i].time != null) {
        out.push({ time: toLWTime(ohlcv[i].time), value: val });
      }
    }
    return out;
  }

  /** Build MACD (3-series) data from indicators object.
   *  Backend returns macd, macd_histogram, macd_signal as arrays of {time, value} objects.
   */
  function buildMACD(ind, ohlcv) {
    var hist = [], line = [], signal = [];
    if (!ind || !ohlcv) return { hist: hist, line: line, signal: signal };
    var macdLineArr   = ind.macd || [];
    var macdHistArr   = ind.macd_histogram || ind.macdHistogram || [];
    var macdSignalArr = ind.macd_signal || ind.macdSignal || [];
    var len = ohlcv.length;
    for (var i = 0; i < len; i++) {
      var t = ohlcv[i] && ohlcv[i].time;
      if (t == null) continue;
      var time = toLWTime(t);

      var histRaw = macdHistArr[i];
      if (histRaw != null) {
        var histVal = (typeof histRaw === 'object') ? histRaw.value : histRaw;
        if (isFinite(histVal)) {
          hist.push({ time: time, value: histVal, color: histVal >= 0 ? C.macdHistUp : C.macdHistDown });
        }
      }

      var lineRaw = macdLineArr[i];
      if (lineRaw != null) {
        var lineVal = (typeof lineRaw === 'object') ? lineRaw.value : lineRaw;
        if (isFinite(lineVal)) {
          line.push({ time: time, value: lineVal });
        }
      }

      var sigRaw = macdSignalArr[i];
      if (sigRaw != null) {
        var sigVal = (typeof sigRaw === 'object') ? sigRaw.value : sigRaw;
        if (isFinite(sigVal)) {
          signal.push({ time: time, value: sigVal });
        }
      }
    }
    return { hist: hist, line: line, signal: signal };
  }

  /** Build constant-value level data (overbought/oversold) */
  function buildLevelData(level, ohlcv) {
    if (!ohlcv || !ohlcv.length) return [];
    var first = ohlcv[0];
    var last  = ohlcv[ohlcv.length - 1];
    if (!first || !last) return [];
    return [
      { time: toLWTime(first.time), value: level },
      { time: toLWTime(last.time),  value: level },
    ];
  }

  /* ──────────────────────────────────────────────────────────────
   * DOM SETUP
   * ────────────────────────────────────────────────────────────── */

  /** Replace the existing <canvas> with a flex-based div container */
  function ensureDOM() {
    var el = document.getElementById('live-canvas');
    if (!el) return null;

    /* If already a DIV, assume we already set up the structure */
    if (el.tagName !== 'CANVAS') {
      var mainPane = document.getElementById('chart-main-pane');
      if (mainPane) return el;  // already initialized
      /* Rebuild: clear and set up structure */
      el.innerHTML = '';
      el.style.cssText = 'width:100%;height:100%;min-height:0;display:flex;flex-direction:column;';
    } else {
      /* Replace canvas with flex container */
      var parent = el.parentElement;
      var wrap = document.createElement('div');
      wrap.id = 'live-canvas';
      wrap.style.cssText = 'width:100%;height:100%;min-height:0;display:flex;flex-direction:column;';
      parent.replaceChild(wrap, el);
      el = wrap;
    }

    /* Create sub-panes */
    var mainDiv = document.createElement('div');
    mainDiv.id = 'chart-main-pane';
    mainDiv.style.cssText = 'flex:1 1 0%;min-height:0;position:relative;overflow:hidden;';

    var rsiDiv = document.createElement('div');
    rsiDiv.id = 'chart-rsi-pane';
    rsiDiv.style.cssText = 'flex:0 0 88px;min-height:88px;border-top:1px solid ' + C.border + ';position:relative;overflow:hidden;';

    var macdDiv = document.createElement('div');
    macdDiv.id = 'chart-macd-pane';
    macdDiv.style.cssText = 'flex:0 0 96px;min-height:96px;border-top:1px solid ' + C.border + ';position:relative;overflow:hidden;';

    el.appendChild(mainDiv);
    el.appendChild(rsiDiv);
    el.appendChild(macdDiv);

    return el;
  }

  /* ──────────────────────────────────────────────────────────────
   * TOOLTIP
   * ────────────────────────────────────────────────────────────── */

  /** Build the hover tooltip (dataviz step 5) */
  function createTooltip() {
    if (document.getElementById('chart-tooltip')) return;
    tooltipEl = document.createElement('div');
    tooltipEl.id = 'chart-tooltip';
    tooltipEl.style.cssText = [
      'position:absolute',
      'display:none',
      'z-index:100',
      'pointer-events:none',
      'background:' + C.surface,
      'border:1px solid ' + C.border,
      'border-radius:6px',
      'padding:8px 12px',
      'font:11px/1.5 "JetBrains Mono",monospace',
      'color:' + C.text,
      'box-shadow:0 4px 20px rgba(0,0,0,0.55)',
      'white-space:nowrap',
      'transform:translate(14px, -50%)',
      'backdrop-filter:blur(8px)',
      '-webkit-backdrop-filter:blur(8px)',
    ].join(';');

    var container = document.getElementById('chart-main-pane') || document.body;
    container.appendChild(tooltipEl);
  }

  /** Format tooltip content for a given time position */
  function buildTooltipHTML(time, ohlcvAtTime, ind) {
    if (!ohlcvAtTime) return '';

    var dt = new Date((time < 1000000000000 ? time * 1000 : time));
    var timeStr = dt.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: '2-digit',
    }) + ' ' + dt.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit',
    });

    var O = ohlcvAtTime.open   != null ? ohlcvAtTime.open.toFixed(2)   : '--';
    var H = ohlcvAtTime.high   != null ? ohlcvAtTime.high.toFixed(2)   : '--';
    var L = ohlcvAtTime.low    != null ? ohlcvAtTime.low.toFixed(2)    : '--';
    var Cv= ohlcvAtTime.close  != null ? ohlcvAtTime.close.toFixed(2)  : '--';
    var V = ohlcvAtTime.volume != null ? ohlcvAtTime.volume.toLocaleString() : '--';

    var closeNum = ohlcvAtTime.close;
    var polarity = closeNum >= ohlcvAtTime.open ? C.bull : C.bear;

    var html = '<div style="color:' + C.textLight + ';font-weight:600;margin-bottom:5px;">'
      + timeStr + '</div>';

    /* OHLCV row — values lead, labels follow (dataviz interaction rule) */
    html += '<div style="display:grid;grid-template-columns:auto auto auto auto;gap:2px 10px;">';
    html +=   '<span style="color:' + C.text + ';">O</span><span style="color:' + C.textLight + ';text-align:right;">' + O + '</span>';
    html +=   '<span style="color:' + C.text + ';">H</span><span style="color:' + C.textLight + ';text-align:right;">' + H + '</span>';
    html +=   '<span style="color:' + C.text + ';">L</span><span style="color:' + C.textLight + ';text-align:right;">' + L + '</span>';
    html +=   '<span style="color:' + C.text + ';">C</span><span style="color:' + polarity + ';text-align:right;font-weight:700;">' + Cv + '</span>';
    html += '</div>';
    html += '<div style="margin-top:3px;color:' + C.text + ';">Vol: <span style="color:' + C.textLight + ';">' + V + '</span></div>';

    /* Indicator values for this time */
    if (ind) {
      var rsiRaw = ind.rsi ? ind.rsi[ohlcvAtTime._idx] : null;
      var rsiVal = (rsiRaw != null && typeof rsiRaw === 'object') ? rsiRaw.value : rsiRaw;
      if (rsiVal != null && isFinite(rsiVal)) {
        var rsiColor = rsiVal > 70 ? C.bear : rsiVal < 30 ? C.bull : C.text;
        html += '<div style="margin-top:3px;"><span style="color:' + C.sma20 + ';">RSI(14)</span> <span style="color:' + rsiColor + ';font-weight:600;">' + Number(rsiVal).toFixed(1) + '</span></div>';
      }

      var macdArr = ind.macd;
      if (macdArr && macdArr[ohlcvAtTime._idx] != null) {
        var macdRaw = macdArr[ohlcvAtTime._idx];
        var macdVal = (typeof macdRaw === 'object') ? macdRaw.value : macdRaw;
        if (isFinite(macdVal)) {
          html += '<div style="margin-top:1px;"><span style="color:' + C.macdLine + ';">MACD</span> <span style="color:' + C.textLight + ';">' + Number(macdVal).toFixed(2) + '</span></div>';
        }
      }
    }

    return html;
  }

  /* ──────────────────────────────────────────────────────────────
   * LEGEND (dataviz step 6 — accessibility)
   * ────────────────────────────────────────────────────────────── */

  function createLegend() {
    if (document.getElementById('chart-legend')) return;
    legendEl = document.createElement('div');
    legendEl.id = 'chart-legend';
    legendEl.style.cssText = [
      'position:absolute',
      'top:6px',
      'left:10px',
      'z-index:10',
      'display:flex',
      'flex-wrap:wrap',
      'gap:6px 12px',
      'font:10px/1.4 "JetBrains Mono",monospace',
      'color:' + C.text,
      'pointer-events:none',
      'user-select:none',
    ].join(';');

    var items = [
      { label: 'SMA20', color: C.sma20 },
      { label: 'SMA50', color: C.sma50 },
      { label: 'EMA20', color: C.ema20, style: 'dashed' },
      { label: 'BB',    color: C.bbLine },
      { label: 'VWAP',  color: C.vwap },
    ];

    for (var i = 0; i < items.length; i++) {
      var item = items[i];
      var span = document.createElement('span');
      span.style.cssText = 'display:inline-flex;align-items:center;gap:4px;';

      var swatch = document.createElement('span');
      swatch.style.cssText = 'display:inline-block;width:14px;height:2px;background:' + item.color + ';';
      if (item.style === 'dashed') {
        swatch.style.background = 'repeating-linear-gradient(90deg,' + item.color + ' 0,' + item.color + ' 4px,transparent 4px,transparent 7px)';
      }
      span.appendChild(swatch);
      span.appendChild(document.createTextNode(item.label));
      legendEl.appendChild(span);
    }

    var container = document.getElementById('chart-main-pane') || document.body;
    container.appendChild(legendEl);
  }

  /* ──────────────────────────────────────────────────────────────
   * SUB-PANE LABELS (RSI / MACD)
   * ────────────────────────────────────────────────────────────── */

  function createPaneLabels() {
    /* RSI label */
    rsiOverlayEl = document.createElement('div');
    rsiOverlayEl.id = 'chart-rsi-label';
    rsiOverlayEl.style.cssText = [
      'position:absolute',
      'top:3px',
      'left:6px',
      'z-index:5',
      'font:9px/1 "JetBrains Mono",monospace',
      'color:' + C.text,
      'pointer-events:none',
      'user-select:none',
      'opacity:0.8',
    ].join(';');
    rsiOverlayEl.textContent = 'RSI(14)';
    var rsiPane = document.getElementById('chart-rsi-pane');
    if (rsiPane) rsiPane.appendChild(rsiOverlayEl);

    /* MACD label */
    macdOverlayEl = document.createElement('div');
    macdOverlayEl.id = 'chart-macd-label';
    macdOverlayEl.style.cssText = [
      'position:absolute',
      'top:3px',
      'left:6px',
      'z-index:5',
      'font:9px/1 "JetBrains Mono",monospace',
      'color:' + C.text,
      'pointer-events:none',
      'user-select:none',
      'opacity:0.8',
    ].join(';');
    macdOverlayEl.textContent = 'MACD(12,26,9)';
    var macdPane = document.getElementById('chart-macd-pane');
    if (macdPane) macdPane.appendChild(macdOverlayEl);
  }

  /* ──────────────────────────────────────────────────────────────
   * CHART FACTORIES
   * ────────────────────────────────────────────────────────────── */

  /** LW chart options shared across all panes */
  function baseChartOptions(container) {
    return {
      width: container.clientWidth || 600,
      height: container.clientHeight || 300,
      layout: {
        background: { color: C.surface },
        textColor: C.text,
        fontSize: 9,
        fontFamily: '-apple-system, BlinkMacSystemFont, "JetBrains Mono", monospace',
      },
      grid: {
        vertLines: { color: C.gridLine, style: 1 },
        horzLines: { color: C.gridLine, style: 1 },
      },
      crosshair: {
        mode: 0, /* CrosshairMode.Normal */
        vertLine: { color: C.crosshair, width: 1, style: 2, labelBackgroundColor: C.surface },
        horzLine: { color: C.crosshair, width: 1, style: 2, labelBackgroundColor: C.surface },
      },
      handleScroll: false,
      handleScale: false,
      watermark: { visible: false },
    };
  }

  /** Create the main candlestick chart with all overlay indicators */
  function createMainChartInstance(container) {
    var opts = baseChartOptions(container);
    opts.rightPriceScale = {
      borderColor: C.border,
      scaleMargins: { top: 0.06, bottom: 0.18 },
    };
    opts.leftPriceScale = { visible: false };
    opts.timeScale = {
      borderColor: C.border,
      timeVisible: true,
      secondsVisible: false,
      fixLeftEdge: true,
      fixRightEdge: true,
    };

    var chart = LightweightCharts.createChart(container, opts);

    /* 1. Candlestick series — the primary form */
    var cs = chart.addCandlestickSeries({
      upColor: C.bull,
      downColor: C.bear,
      borderUpColor: C.bull,
      borderDownColor: C.bear,
      wickUpColor: C.bull,
      wickDownColor: C.bear,
      priceLineVisible: false,
      lastValueVisible: true,
    });

    /* 2. Volume — sequential, one hue, recessive */
    var vol = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      priceLineVisible: false,
      lastValueVisible: false,
    });
    var volScale = chart.priceScale('volume');
    if (volScale) {
      volScale.applyOptions({ scaleMargins: { top: 0.88, bottom: 0 } });
    }

    /* 3. SMA20 — cyan (categorical: identity) */
    var sma20 = chart.addLineSeries({
      color: C.sma20,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 2,
      crosshairMarkerBorderColor: C.sma20,
      crosshairMarkerBackgroundColor: C.surface,
    });

    /* 4. SMA50 — green (categorical) */
    var sma50 = chart.addLineSeries({
      color: C.sma50,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 2,
      crosshairMarkerBorderColor: C.sma50,
      crosshairMarkerBackgroundColor: C.surface,
    });

    /* 5. EMA20 — white dashed (categorical + style contrast) */
    var ema20 = chart.addLineSeries({
      color: C.ema20,
      lineWidth: 1,
      lineStyle: 2, /* LineStyle.Dashed */
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 2,
      crosshairMarkerBorderColor: C.ema20,
      crosshairMarkerBackgroundColor: C.surface,
    });

    /* 6. Bollinger Bands — upper (area fill) + lower (line) */
    var bbUpper = chart.addAreaSeries({
      lineColor: C.bbLine,
      topColor: C.bbFill,
      bottomColor: 'rgba(0,230,118,0.005)',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    var bbLower = chart.addLineSeries({
      color: C.bbLine,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    /* 7. VWAP — amber */
    var vwap = chart.addLineSeries({
      color: C.vwap,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 2,
      crosshairMarkerBorderColor: C.vwap,
      crosshairMarkerBackgroundColor: C.surface,
    });

    return {
      chart: chart,
      cs: cs,
      vol: vol,
      sma20: sma20,
      sma50: sma50,
      ema20: ema20,
      bbUpper: bbUpper,
      bbLower: bbLower,
      vwap: vwap,
    };
  }

  /** Create the RSI sub-chart pane */
  function createRSIInstance(container) {
    var opts = baseChartOptions(container);
    opts.rightPriceScale = {
      borderColor: C.border,
      scaleMargins: { top: 0.12, bottom: 0.12 },
    };
    opts.timeScale = { borderColor: C.border, visible: false };

    var chart = LightweightCharts.createChart(container, opts);

    /* RSI line */
    var rsi = chart.addLineSeries({
      color: C.rsiLine,
      lineWidth: 1.5,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: C.rsiLine,
      crosshairMarkerBackgroundColor: C.surface,
    });

    /* Overbought 70 (dashed) */
    var ob = chart.addLineSeries({
      color: C.rsiOb,
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    /* Oversold 30 (dashed) */
    var os = chart.addLineSeries({
      color: C.rsiOs,
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    return { chart: chart, rsi: rsi, overbought: ob, oversold: os };
  }

  /** Create the MACD sub-chart pane */
  function createMACDInstance(container) {
    var opts = baseChartOptions(container);
    opts.rightPriceScale = {
      borderColor: C.border,
      scaleMargins: { top: 0.15, bottom: 0.12 },
    };
    opts.timeScale = { borderColor: C.border, visible: false };

    var chart = LightweightCharts.createChart(container, opts);

    /* MACD histogram */
    var hist = chart.addHistogramSeries({
      priceFormat: { type: 'custom', formatter: function (v) { return v != null ? v.toFixed(2) : '--'; } },
      priceLineVisible: false,
      lastValueVisible: false,
    });

    /* MACD line */
    var line = chart.addLineSeries({
      color: C.macdLine,
      lineWidth: 1.5,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: C.macdLine,
      crosshairMarkerBackgroundColor: C.surface,
    });

    /* MACD signal line */
    var signal = chart.addLineSeries({
      color: C.macdSignal,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: C.macdSignal,
      crosshairMarkerBackgroundColor: C.surface,
    });

    return { chart: chart, hist: hist, line: line, signal: signal };
  }

  /* ──────────────────────────────────────────────────────────────
   * CROSSHAIR + TOOLTIP BINDING
   * ────────────────────────────────────────────────────────────── */

  /** Subscribe to main chart crosshair moves to show tooltip */
  function bindCrosshair() {
    if (!mainChart || !tooltipEl) return;

    mainChart.subscribeCrosshairMove(function (param) {
      if (!tooltipEl) return;

      var time = param.time;
      var point = param.point;

      /* Hide tooltip when crosshair leaves chart */
      if (!time || !point || point.x < 0 || point.y < 0) {
        tooltipEl.style.display = 'none';
        return;
      }

      /* Find nearest OHLCV row by time */
      var chartData = chartDataCache;
      if (!chartData || !chartData.ohlcv) {
        tooltipEl.style.display = 'none';
        return;
      }

      var ohlcv = chartData.ohlcv;
      var ind = chartData.indicators || {};
      var lwTime = toLWTime(time);
      var matched = null;

      for (var i = 0; i < ohlcv.length; i++) {
        if (toLWTime(ohlcv[i].time) === lwTime) {
          matched = ohlcv[i];
          matched._idx = i;
          break;
        }
      }

      if (!matched) {
        tooltipEl.style.display = 'none';
        return;
      }

      /* Build and position tooltip */
      var html = buildTooltipHTML(time, matched, ind);
      tooltipEl.innerHTML = html;
      tooltipEl.style.display = 'block';

      /* Position relative to the main pane */
      var mainPane = document.getElementById('chart-main-pane');
      if (mainPane) {
        var rect = mainPane.getBoundingClientRect();
        var left = point.x + 14;
        var top  = point.y;

        /* Keep within pane bounds */
        var tooltipW = tooltipEl.offsetWidth || 200;
        if (left + tooltipW + 10 > rect.width) {
          left = point.x - tooltipW - 16;
        }
        if (top < 20) top = 20;
        if (top > rect.height - 20) top = rect.height - 20;

        tooltipEl.style.left = left + 'px';
        tooltipEl.style.top  = top + 'px';
      }
    });
  }

  /* ──────────────────────────────────────────────────────────────
   * TIME SCALE SYNC (sub-panes follow main pane)
   * ────────────────────────────────────────────────────────────── */

  /** Subscribe main chart time-scale changes to sync RSI and MACD panes */
  function bindTimeScaleSync() {
    if (!mainChart || !rsiChart || !macdChart) return;

    mainChart.timeScale().subscribeVisibleTimeRangeChange(function (range) {
      if (range) {
        try { rsiChart.timeScale().setVisibleRange(range); } catch (e) { /* ignore */ }
        try { macdChart.timeScale().setVisibleRange(range); } catch (e) { /* ignore */ }
      }
    });
  }

  /* ──────────────────────────────────────────────────────────────
   * RESIZE OBSERVER
   * ────────────────────────────────────────────────────────────── */

  function setupResize() {
    var wrap = document.getElementById('live-canvas');
    if (!wrap) return;

    if (resizeRO) resizeRO.disconnect();

    resizeRO = new ResizeObserver(function () {
      requestAnimationFrame(function () {
        var mainPane = document.getElementById('chart-main-pane');
        var rsiPane  = document.getElementById('chart-rsi-pane');
        var macdPane = document.getElementById('chart-macd-pane');

        if (mainChart && mainPane) {
          mainChart.applyOptions({ width: mainPane.clientWidth, height: mainPane.clientHeight });
        }
        if (rsiChart && rsiPane) {
          rsiChart.applyOptions({ width: rsiPane.clientWidth, height: rsiPane.clientHeight });
        }
        if (macdChart && macdPane) {
          macdChart.applyOptions({ width: macdPane.clientWidth, height: macdPane.clientHeight });
        }
      });
    });

    resizeRO.observe(wrap);
  }

  /* ──────────────────────────────────────────────────────────────
   * RENDER — apply SZ.state.chartData to all series
   * ────────────────────────────────────────────────────────────── */

  function applyChartData() {
    var cd = window.SZ && window.SZ.state && window.SZ.state.chartData;
    if (!cd || !cd.ohlcv || !cd.ohlcv.length) return;

    /* Lazy init if needed */
    if (!isInitialized) {
      initCharts();
    }

    if (isDestroyed) return;

    chartDataCache = cd;
    var ohlcv = cd.ohlcv;
    var ind = cd.indicators || {};

    /* Main chart series */
    try { candleSeries.setData(buildOHLCV(ohlcv)); } catch (e) { /* ignore — data shape mismatch */ }
    try { volumeSeries.setData(buildVolume(ohlcv)); } catch (e) { /* ignore */ }

    try { sma20Series.setData(buildLineData(ind.sma_20 || ind.sma20, ohlcv)); } catch (e) { /* ignore */ }
    try { sma50Series.setData(buildLineData(ind.sma_50 || ind.sma50, ohlcv)); } catch (e) { /* ignore */ }
    try { ema20Series.setData(buildLineData(ind.ema_20 || ind.ema20, ohlcv)); } catch (e) { /* ignore */ }

    /* Bollinger Bands */
    var bbUpper = ind.bollinger_upper || ind.bb_upper || [];
    var bbLower = ind.bollinger_lower || ind.bb_lower || [];
    try { bbUpperSeries.setData(buildLineData(bbUpper, ohlcv)); } catch (e) { /* ignore */ }
    try { bbLowerSeries.setData(buildLineData(bbLower, ohlcv)); } catch (e) { /* ignore */ }

    try { vwapSeries.setData(buildLineData(ind.vwap, ohlcv)); } catch (e) { /* ignore */ }

    /* RSI sub-pane */
    try {
      rsiLineSeries.setData(buildLineData(ind.rsi, ohlcv));
      rsiObSeries.setData(buildLevelData(70, ohlcv));
      rsiOsSeries.setData(buildLevelData(30, ohlcv));
    } catch (e) { /* ignore */ }

    /* MACD sub-pane */
    var macdData = buildMACD(ind, ohlcv);
    try {
      macdHistSeries.setData(macdData.hist);
      macdLineSeries.setData(macdData.line);
      macdSignalSeries.setData(macdData.signal);
    } catch (e) { /* ignore */ }

    /* Fit content in view */
    try { mainChart.timeScale().fitContent(); } catch (e) { /* ignore */ }
  }

  /* ──────────────────────────────────────────────────────────────
   * INIT CHARTS
   * ────────────────────────────────────────────────────────────── */

  function initCharts() {
    if (isInitialized) return;
    isDestroyed = false;

    var container = ensureDOM();
    if (!container) return;

    var mainPane  = document.getElementById('chart-main-pane');
    var rsiPane   = document.getElementById('chart-rsi-pane');
    var macdPane  = document.getElementById('chart-macd-pane');
    if (!mainPane || !rsiPane || !macdPane) return;

    /* Main chart */
    var m = createMainChartInstance(mainPane);
    mainChart     = m.chart;
    candleSeries  = m.cs;
    volumeSeries  = m.vol;
    sma20Series   = m.sma20;
    sma50Series   = m.sma50;
    ema20Series   = m.ema20;
    bbUpperSeries = m.bbUpper;
    bbLowerSeries = m.bbLower;
    vwapSeries    = m.vwap;

    /* RSI sub-pane */
    var r = createRSIInstance(rsiPane);
    rsiChart      = r.chart;
    rsiLineSeries = r.rsi;
    rsiObSeries   = r.overbought;
    rsiOsSeries   = r.oversold;

    /* MACD sub-pane */
    var md = createMACDInstance(macdPane);
    macdChart        = md.chart;
    macdHistSeries   = md.hist;
    macdLineSeries   = md.line;
    macdSignalSeries = md.signal;

    /* Chrome */
    createTooltip();
    createLegend();
    createPaneLabels();

    /* Bindings */
    bindCrosshair();
    bindTimeScaleSync();
    setupResize();

    isInitialized = true;
  }

  /* ──────────────────────────────────────────────────────────────
   * PUBLIC API
   * ────────────────────────────────────────────────────────────── */

  /**
   * SZ.chart.load(ticker, timeframe)
   * Primary API — fetches chart data and renders it.
   * Delegates to the existing SZ.loadChart for consistency with
   * cockpit integration, ticker routing, and state management.
   */
  function load(ticker, timeframe) {
    if (!ticker) return;
    if (window.SZ && window.SZ.loadChart) {
      return window.SZ.loadChart(ticker);
    }
    /* Fallback: direct fetch */
    var tf = timeframe || '6M';
    if (window.SZ && window.SZ.api && window.SZ.api.fetchChartData) {
      window.SZ.api.fetchChartData(ticker, tf).then(function (data) {
        if (window.SZ && window.SZ.state) {
          window.SZ.state.chartData = data;
          applyChartData();
        }
      });
    }
  }

  /**
   * SZ.chart.update(candle)
   * Real-time SSE merge — merges a single new candle and
   * efficiently updates the chart.
   */
  function update(candle) {
    if (!candle || !candle.time) return;
    var cd = window.SZ && window.SZ.state && window.SZ.state.chartData;
    if (!cd || !cd.ohlcv) return;

    /* Merge candle into state (dedup by time) */
    var ohlcv = cd.ohlcv;
    var replaced = false;
    for (var i = ohlcv.length - 1; i >= 0; i--) {
      if (ohlcv[i].time === candle.time) {
        ohlcv[i] = candle;
        replaced = true;
        break;
      }
    }
    if (!replaced) {
      ohlcv.push(candle);
      if (ohlcv.length > 500) ohlcv.splice(0, ohlcv.length - 500);
    }

    /* Efficient update: only update the last candle/indicator point */
    if (!isDestroyed && isInitialized) {
      try {
        var time = toLWTime(candle.time);
        candleSeries.update({
          time: time,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
        });

        if (candle.volume != null) {
          volumeSeries.update({
            time: time,
            value: candle.volume,
            color: candle.close >= candle.open ? C.volBull : C.volBear,
          });
        }

        /* Update indicator last values if present */
        if (candle.indicators) {
          var ci = candle.indicators;
          if (ci.sma_20 != null) sma20Series.update({ time: time, value: ci.sma_20 });
          if (ci.sma_50 != null) sma50Series.update({ time: time, value: ci.sma_50 });
          if (ci.ema_20 != null) ema20Series.update({ time: time, value: ci.ema_20 });
          if (ci.vwap  != null) vwapSeries.update({ time: time, value: ci.vwap });
          if (ci.rsi   != null) rsiLineSeries.update({ time: time, value: ci.rsi });
        }
      } catch (e) { /* ignore transient update errors */ }

      /* Refresh cache reference */
      chartDataCache = cd;
    }
  }

  /**
   * SZ.chart.destroy()
   * Full teardown — removes charts, observers, tooltip.
   */
  function destroy() {
    isDestroyed = true;
    isInitialized = false;

    if (resizeRO) { resizeRO.disconnect(); resizeRO = null; }

    var charts = [mainChart, rsiChart, macdChart];
    for (var i = 0; i < charts.length; i++) {
      if (charts[i]) {
        try { charts[i].remove(); } catch (e) { /* ignore */ }
      }
    }
    mainChart = null; rsiChart = null; macdChart = null;

    var els = ['chart-tooltip', 'chart-legend', 'chart-rsi-label', 'chart-macd-label'];
    for (var j = 0; j < els.length; j++) {
      var el = document.getElementById(els[j]);
      if (el && el.parentNode) el.parentNode.removeChild(el);
    }
    tooltipEl = null; legendEl = null;
    rsiOverlayEl = null; macdOverlayEl = null;
    chartDataCache = null;
  }

  /**
   * SZ.chart.resize()
   * Force resize re-evaluation (useful after layout changes).
   */
  function manualResize() {
    if (resizeRO) {
      var wrap = document.getElementById('live-canvas');
      if (wrap) resizeRO.observe(wrap);
    }
  }

  /* ──────────────────────────────────────────────────────────────
   * BACKWARD COMPATIBILITY
   * ────────────────────────────────────────────────────────────── */

  /*
   * These replace the Canvas 2D exports from render-chart.js
   * and render-candles.js. They read SZ.state.chartData and
   * forward to the WebGL-powered applyChartData().
   */
  window.SZ.renderChart = function () {
    if (isDestroyed) return;
    if (!isInitialized) initCharts();
    applyChartData();
  };

  window.SZ.drawLiveCandles = function () {
    /* Same as renderChart — the LW chart handles all rendering */
    if (isDestroyed) return;
    if (!isInitialized) initCharts();
    applyChartData();
  };

  /* ──────────────────────────────────────────────────────────────
   * EXPORT SZ.chart API
   * ────────────────────────────────────────────────────────────── */

  window.SZ.chart = {
    load:    load,
    update:  update,
    destroy: destroy,
    resize:  manualResize,
    _apply:  applyChartData,  // internal: for dev / debug
  };

  /* ──────────────────────────────────────────────────────────────
   * AUTO-INIT ON DOM READY
   * ────────────────────────────────────────────────────────────── */

  function autoInit() {
    /* Pre-initialize DOM structure so it's ready when data arrives */
    try {
      ensureDOM();
    } catch (e) {
      /* DOM might not be ready yet; initChart will be called lazily */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  console.log('[SZ.chart] WebGL chart module loaded (Lightweight Charts).');
})();
