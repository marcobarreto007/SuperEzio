/* SuperEzio — canonical operational status consumers */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function mark(el, state) { if (!el) return; el.classList.remove("is-ok", "is-error", "is-warn"); el.classList.add(state || "is-warn"); }
  function setItem(id, text, state) { var el = $(id); if (!el) return; el.textContent = text; mark(el, state); }
  function tone(state) { if (["online", "live", "healthy", "complete"].indexOf(state) >= 0) return "is-ok"; if (["offline", "error"].indexOf(state) >= 0) return "is-error"; return "is-warn"; }
  function upper(value) { return String(value || "unknown").toUpperCase(); }

  function render(snapshot) {
    if (!snapshot) return;
    var core = snapshot.core || { state: "unknown" };
    var ceo = snapshot.ceo || { state: "unknown" };
    var data = snapshot.data || { state: "unknown" };
    var broker = snapshot.broker || { state: "unknown", provider: "IBKR" };
    var pipeline = snapshot.pipeline || { state: "idle" };
    var mode = upper(snapshot.mode || "research");
    var guardrails = snapshot.guardrails || {};
    setItem("statusbar-ceo", "CORE: " + upper(core.state), tone(core.state));
    setItem("statusbar-genie", "CEO: " + upper(ceo.state), tone(ceo.state));
    setItem("statusbar-deep", "DATA: " + upper(data.state) + (data.asOf ? " · " + new Date(data.asOf).toLocaleTimeString() : ""), tone(data.state));
    setItem("statusbar-ibkr", upper(broker.provider) + ": " + upper(broker.state), tone(broker.state));
    setItem("statusbar-guardrails", "MODE: " + mode, mode === "PAPER" ? "is-warn" : "is-ok");
    setItem("statusbar-latency", "PIPELINE: " + upper(pipeline.state), tone(pipeline.state));
    var marketStatus = $("live-status");
    if (marketStatus) marketStatus.textContent = "DATA " + upper(data.state);
    var marketTs = $("live-ts");
    if (marketTs) marketTs.textContent = data.asOf || "";
    var label = $("cockpit-connection");
    if (label) { label.textContent = "CORE " + upper(core.state) + " · " + mode + " MODE · " + upper(broker.provider) + " " + upper(broker.state); label.classList.toggle("is-online", core.state === "online"); }
    var brokerLabel = $("broker-status-label");
    if (brokerLabel) brokerLabel.textContent = upper(broker.provider) + " " + upper(broker.state);
    if (guardrails.passed != null && guardrails.total != null) { var summary = $("guardrails-summary"); if (summary) summary.textContent = guardrails.passed + "/" + guardrails.total; }
  }

  function refresh() { return window.SZ.health && window.SZ.health.check ? window.SZ.health.check() : Promise.resolve(null); }
  function init() { if (window.SZ.subscribe) window.SZ.subscribe("operational-snapshot", render); if (window.SZ.state && window.SZ.state.operationalSnapshot) render(window.SZ.state.operationalSnapshot); }
  window.SZ.statusBar = { refresh: refresh, render: render };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
