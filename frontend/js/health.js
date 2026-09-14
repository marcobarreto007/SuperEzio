/* SuperEzio — canonical operational truth snapshot */
(function () {
  "use strict";

  function componentState(hasResult, pipelineState) {
    if (hasResult) return "complete";
    if (pipelineState === "running") return "running";
    if (pipelineState === "error") return "error";
    return "ready";
  }

  function chartTimestamp(chart) {
    return chart && (chart.as_of || chart.fetched_at || chart.timestamp || chart.last_update) || null;
  }

  function dataState(chart) {
    if (!chart) return { state: "unknown", asOf: null };
    var asOf = chartTimestamp(chart);
    var candles = Array.isArray(chart.ohlcv) ? chart.ohlcv.length : 0;
    if (!candles) return { state: "offline", asOf: asOf };
    if (!asOf) return { state: "degraded", asOf: null };
    var parsed = new Date(asOf).getTime();
    if (!isFinite(parsed)) return { state: "degraded", asOf: asOf };
    return { state: Date.now() - parsed > 15 * 60 * 1000 ? "stale" : "live", asOf: asOf };
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
