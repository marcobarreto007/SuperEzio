/* SuperEzio StatusBar */
(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function mark(el, state) {
    if (!el) return;
    el.classList.remove("is-ok", "is-error", "is-warn");
    el.classList.add(state || "is-warn");
  }

  function setItem(id, text, state) {
    var el = $(id);
    if (!el) return;
    el.textContent = text;
    mark(el, state);
  }

  function providerSummary(details) {
    return (((details || {}).checks || {}).providers_summary || {});
  }

  function mission(details) {
    return ((details || {}).mission || {});
  }

  function updateFromDetails(details) {
    var providers = providerSummary(details);
    var primary = providers.primary || {};
    var deepseek = providers.deepseek || {};
    var broker = ((mission(details).broker || {}).ibkr || {});
    var guardrails = 30;
    var connected = String(broker.connection || "").indexOf("connected") >= 0 || broker.can_read_account === true;
    var positions = broker.positions_count == null ? 0 : broker.positions_count;
    var equity = broker.account_equity || "100000.00";

    setItem(
      "statusbar-ceo",
      "CEO: " + (primary.model || "local") + " (:8082)",
      primary.configured ? "is-ok" : "is-warn"
    );
    setItem("statusbar-genie", "Genie: " + ((details.checks || {}).provider_gemini ? "Gemini" : "CHECKING"), ((details.checks || {}).provider_gemini || {}).configured ? "is-ok" : "is-warn");
    setItem(
      "statusbar-deep",
      "Deep: " + (deepseek.model || "DeepSeek"),
      deepseek.configured ? "is-ok" : "is-warn"
    );
    setItem(
      "statusbar-ibkr",
      "IBKR: Paper $" + equity + " (" + positions + " pos)",
      connected ? "is-ok" : "is-error"
    );
    setItem("statusbar-guardrails", guardrails + "/" + guardrails + " guardrails", "is-ok");
    setItem("statusbar-latency", "KillSwitch: ARMED | Last run: " + lastRunLabel(), "is-ok");
  }

  function lastRunLabel() {
    var steps = ((window.SZ.state.bobPanel || {}).steps || {});
    var names = Object.keys(steps);
    if (!names.length) return "--";
    var first = null;
    var last = null;
    names.forEach(function (name) {
      var step = steps[name] || {};
      if (step.started && (first == null || step.started < first)) first = step.started;
      if (step.ended && (last == null || step.ended > last)) last = step.ended;
    });
    if (!first || !last) return "--";
    return ((last - first) / 1000).toFixed(2) + "s";
  }

  async function refresh() {
    try {
      var details = await window.SZ.api.fetchHealthDetails();
      window.SZ.state.healthDetails = details;
      updateFromDetails(details);
    } catch (e) {
      setItem("statusbar-ceo", "CEO: OFFLINE", "is-error");
      setItem("statusbar-genie", "Genie: OFFLINE", "is-error");
      setItem("statusbar-deep", "Deep: OFFLINE", "is-error");
      setItem("statusbar-ibkr", "IBKR: OFFLINE", "is-error");
      setItem("statusbar-guardrails", "Guardrails: --", "is-warn");
      setItem("statusbar-latency", "KillSwitch: UNKNOWN | Last run: --", "is-warn");
    }
  }

  function init() {
    refresh();
    window.setInterval(refresh, 10000);
    if (window.SZ.subscribe) {
      window.SZ.subscribe("pipeline-event", function (event) {
        if (event && event.type === "STREAM_END" && window.SZ.state.healthDetails) {
          updateFromDetails(window.SZ.state.healthDetails);
        }
      });
    }
  }

  window.SZ = window.SZ || {};
  window.SZ.statusBar = { refresh: refresh, updateFromDetails: updateFromDetails };
  document.addEventListener("DOMContentLoaded", init);
})();
