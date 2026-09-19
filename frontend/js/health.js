/* SuperEzio — canonical operational truth snapshot */
(function () {
  "use strict";

  function componentState(hasResult, pipelineState) {
    if (hasResult) return "complete";
    if (pipelineState === "running") return "running";
    if (pipelineState === "error") return "error";
    return "ready";
  }

  /* Two stamp shapes reach this file and both must read as the same fact:
     `server_ts` is epoch SECONDS as an int — the REST/SSE convention pinned by
     tests/test_chart_data_times.py — while as_of/fetched_at/timestamp/last_update
     carry ISO strings or epoch ms. Reading server_ts raw would date it to 1970
     and render a fresh chart as "stale", so every candidate goes through
     parseStamp. A payload with no stamp at all is still datable from its own
     last bar: the bars are the evidence, and refusing to look at them is what
     made a healthy chart report "degraded" on every ticker, forever. */
  var STAMP_KEYS = ["as_of", "fetched_at", "timestamp", "last_update", "server_ts"];

  function parseStamp(value) {
    if (value == null) return null;
    if (typeof value === "number") {
      if (!isFinite(value) || value <= 0) return null;
      return value < 1e11 ? value * 1000 : value;   // seconds vs milliseconds
    }
    if (typeof value === "string") {
      var s = value.trim();
      if (!s) return null;
      var t = Date.parse(s);
      return isFinite(t) ? t : null;
    }
    return null;
  }

  function lastCandleTime(chart) {
    var rows = Array.isArray(chart && chart.ohlcv) ? chart.ohlcv : [];
    for (var i = rows.length - 1; i >= 0; i--) {
      var t = parseStamp(rows[i] && rows[i].time);
      if (t != null) return t;
    }
    return null;
  }

  /* Returns epoch milliseconds, or null when the payload dates itself nowhere. */
  function chartTimestamp(chart) {
    if (!chart) return null;
    for (var i = 0; i < STAMP_KEYS.length; i++) {
      var t = parseStamp(chart[STAMP_KEYS[i]]);
      if (t != null) return t;
    }
    return lastCandleTime(chart);
  }

  function dataState(chart) {
    if (!chart) return { state: "unknown", asOf: null };
    var ms = chartTimestamp(chart);
    var candles = Array.isArray(chart.ohlcv) ? chart.ohlcv.length : 0;
    var asOf = ms == null ? null : new Date(ms).toISOString();
    if (!candles) return { state: "offline", asOf: asOf };
    /* No parseable time anywhere: candles exist but nothing dates them. That is
       the only remaining honest reading of "degraded". */
    if (ms == null) return { state: "degraded", asOf: null };
    return { state: Date.now() - ms > 15 * 60 * 1000 ? "stale" : "live", asOf: asOf };
  }

  function pipelineState() {
    var state = window.SZ.state || {};
    if (state.busy || state.stream === "active") return "running";
    if (state.pipelineError) return "error";
    return "idle";
  }

  function buildSnapshot(details) {
    var state = window.SZ.state || {};
    var checks = (details && details.checks) || {};
    var models = checks.local_models || {};
    var agent = models.agent || {};
    var mission = (details && details.mission) || {};
    var broker = ((mission.broker || {}).ibkr) || {};
    var pipe = pipelineState();
    var chart = dataState(state.chartData);
    var brokerConnected = broker.connection === "connected" || broker.can_read_account === true;
    /* Execution mode is derived from the evidence /health/details really sends
       under mission: paper_trading.active first, then mission.phase /
       paper_trading.mode. It used to read mission.current_policy.phase — a field
       the backend does not carry — so the indexOf("paper") test was always -1 and
       the mode collapsed to "research" whatever the backend said. With no
       evidence the mode stays null: status-bar.js renders that as SEM DADO, and
       an absent fact never becomes a claim. Same two fields status-bar.js uses,
       so both paths agree. */
    var paper = mission.paper_trading || {};
    var phase = String(mission.phase || paper.mode || "").toLowerCase();
    var mode = paper.active === true ? "paper" : (phase ? phase.split("_")[0] : null);
    var guardrails = state.lastGuardrailHub || ((state.deep || {}).guardrails) || null;
    var guardData = guardrails && (guardrails.data || guardrails);
    var guardTotal = guardData && (guardData.total_guardrails || guardData.total);
    var guardSummary = guardData && guardData.summary;
    var guardBlocking = guardSummary && guardSummary.blocking_count;
    var guardPassed = guardTotal != null && guardBlocking != null ? guardTotal - guardBlocking : null;
    var trust = state.lastF51Verdict && window.SZ.trustScore ? window.SZ.trustScore.compute() : null;

    return {
      core: { state: details ? "online" : "offline" },
      ceo: { state: agent.reachable === true ? "online" : (agent.status === "down" ? "offline" : "unknown") },
      data: chart,
      broker: { state: brokerConnected ? "online" : "offline", provider: broker.provider || "IBKR" },
      mode: mode,
      pipeline: { state: pipe, activeNode: state.activePipelineNode || null },
      f51: { state: componentState(Boolean(state.lastF51Verdict), pipe), verdict: state.lastF51Verdict || null },
      sdca: { state: componentState(Boolean(window.SZ.__sdcaState), pipe), verdict: window.SZ.__sdcaState || null },
      neural: { state: componentState(Boolean(window.SZ.__neuralState), pipe), verdict: window.SZ.__neuralState || null },
      trinity: { state: componentState(Boolean(state.lastTrinity), pipe), verdict: state.lastTrinity || null },
      guardrails: {
        state: guardData ? (guardBlocking === 0 ? "healthy" : "review") : "unknown",
        passed: guardPassed,
        total: guardTotal == null ? null : guardTotal
      },
      trust: trust
    };
  }

  async function check() {
    var details = null;
    try {
      details = await SZ.api.fetchHealthDetails();
    } catch (e) { details = null; }
    SZ.state.health = Boolean(details);
    SZ.state.healthDetails = details;
    SZ.state.operationalSnapshot = buildSnapshot(details);
    const dot = document.getElementById("sys-dot");
    if (dot) {
      dot.className = "status-dot " + (SZ.state.health ? "status-dot--on" : "status-dot--off");
      dot.title = SZ.state.health ? "Core online" : "Core offline";
    }
    SZ.publish("operational-snapshot", SZ.state.operationalSnapshot);
    return SZ.state.operationalSnapshot;
  }

  function init() {
    check();
    window.setInterval(check, 10000);
  }

  window.SZ.health = { check: check, buildSnapshot: buildSnapshot };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
