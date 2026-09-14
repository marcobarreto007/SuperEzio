/* SuperEzio — canonical operational status consumers */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function mark(el, state) { if (!el) return; el.classList.remove("is-ok", "is-error", "is-warn"); el.classList.add(state || "is-warn"); }
  function setItem(id, text, state) { var el = $(id); if (!el) return; el.textContent = text; mark(el, state); }
  function tone(state) { if (["online", "live", "healthy", "complete"].indexOf(state) >= 0) return "is-ok"; if (["offline", "error"].indexOf(state) >= 0) return "is-error"; return "is-warn"; }
  function upper(value) { return String(value || "unknown").toUpperCase(); }

  /* Explicit data state map: state → display label and tone */
  var DATA_STATE_MAP = {
    "unknown":     { label: "AGUARDANDO", tone: "is-warn" },
    "offline":     { label: "OFFLINE", tone: "is-warn" },
    "online":      { label: "ONLINE", tone: "is-ok" },
    "live":        { label: "LIVE", tone: "is-ok" },
    "healthy":     { label: "ONLINE", tone: "is-ok" },
    "degraded":    { label: "DEGRADADO", tone: "is-warn" },
    "error":       { label: "ERRO", tone: "is-error" },
    "stale":       { label: "STALE", tone: "is-warn" },
    "fetching":    { label: "CARREGANDO", tone: "is-warn" }
  };

  function getDataStateInfo(state) {
    var key = String(state || "unknown").toLowerCase();
    return DATA_STATE_MAP[key] || DATA_STATE_MAP["unknown"];
  }

  /* A badge may only be as green as its weakest claim: the tone of an item that
     carries two facts (mode + guardrails) is the worst of the two. Default when
     nothing is known is amber, never green. */
  var TONE_RANK = { "is-ok": 1, "is-warn": 2, "is-error": 3 };
  function worstTone(a, b) {
    var ra = TONE_RANK[a] || 2; /* unknown tone counts as warn */
    var rb = TONE_RANK[b] || 2;
    return ra >= rb ? (a || "is-warn") : b;
  }

  function details() { return (window.SZ && window.SZ.state && window.SZ.state.healthDetails) || null; }

  function ibkrDetails() {
    var mission = (details() || {}).mission || {};
    return ((mission.broker || {}).ibkr) || null;
  }

  /* Execution mode comes from the evidence the backend actually sends
     (/health/details -> mission): paper_trading.active and mission.phase.
     snapshot.mode is only the last resort — it is derived from
     mission.current_policy, a field /health/details does not carry.
     The mode is a statement of fact, not a health claim: it only goes amber
     when there is no evidence for it at all. The tone of the whole item is
     decided by the guardrail evidence (worstTone below). */
  function modeLabel(snapshot) {
    var mission = (details() || {}).mission || {};
    var paper = mission.paper_trading || {};
    if (paper.active === true) return { text: "PAPER", tone: "is-ok" };
    var phase = String(mission.phase || paper.mode || "");
    if (phase) return { text: upper(phase.split("_")[0]), tone: "is-ok" };
    var fallback = String((snapshot || {}).mode || "");
    if (fallback) return { text: upper(fallback), tone: "is-ok" };
    return { text: "SEM DADO", tone: "is-warn" };
  }

  /* Broker link tone. OFFLINE is amber, not green and not red:
     - not green: nothing about the link is verified, and no order can be sent;
     - not red: the runtime is built to keep running with the broker down (order
       submission is blocked, not attempted), so it is a state that needs
       attention, not a failure of the system. */
  function brokerInfo(broker) {
    var provider = upper(broker.provider);
    if (provider === "UNKNOWN") provider = "IBKR"; /* same default health.js uses */
    var state = String(broker.state || "unknown").toLowerCase();
    var ibkr = ibkrDetails();
    if (state === "online") return { text: provider + ": ONLINE", tone: "is-ok" };
    if (state === "error") return { text: provider + ": ERRO", tone: "is-error" };
    if (state === "offline") {
      /* "sem execução" is only appended when the backend says so. */
      var blocked = ibkr && ibkr.can_submit_orders !== true;
      return { text: provider + ": OFFLINE" + (blocked ? " · SEM EXECUÇÃO" : ""), tone: "is-warn" };
    }
    return { text: provider + ": SEM DADO", tone: "is-warn" };
  }

  /* Guardrails: only a real Guardrail Hub run is evidence. The backend answers
     status:"unknown" (bob.guardrails) until a run happens — that is "SEM DADO",
     and no total is ever invented. */
  function guardrailEvidence(snapshot) {
    var hub = (window.SZ.state || {}).lastGuardrailHub;
    var snap = (snapshot || {}).guardrails || {};
    if (hub) {
      var summary = hub.summary || {};
      var counts = summary.decision_counts || {};
      var total = hub.total_guardrails != null ? hub.total_guardrails : hub.total;
      var blocking = summary.blocking_count != null ? summary.blocking_count : null;
      var ok = counts.ALLOW != null ? counts.ALLOW
        : (total != null && blocking != null ? total - blocking : null);
      return { source: "hub", ok: ok, total: total != null ? total : null, blocking: blocking };
    }
    var state = String(snap.state || "unknown").toLowerCase();
    if (state === "unknown" || state === "unavailable") return { source: null, ok: null, total: null, blocking: null };
    return { source: "snapshot", ok: snap.passed != null ? snap.passed : null, total: snap.total != null ? snap.total : null, blocking: null };
  }

  function guardrailInfo(snapshot) {
    var e = guardrailEvidence(snapshot);
    if (!e.source || e.total == null || e.total === 0 || e.ok == null) return { text: "SEM DADO", tone: "is-warn" };
    if (e.blocking != null && e.blocking > 0) return { text: e.ok + "/" + e.total, tone: e.blocking > 2 ? "is-error" : "is-warn" };
    return { text: e.ok + "/" + e.total, tone: e.ok >= e.total ? "is-ok" : "is-warn" };
  }

  function render(snapshot) {
    if (!snapshot) return;
    var core = snapshot.core || { state: "unknown" };
    var ceo = snapshot.ceo || { state: "unknown" };
    var data = snapshot.data || { state: "unknown" };
    var broker = snapshot.broker || { state: "unknown", provider: "IBKR" };
    var pipeline = snapshot.pipeline || { state: "idle" };
    var guardrails = snapshot.guardrails || {};
    var modeInfo = modeLabel(snapshot);
    var mode = modeInfo.text;
    var brokerStatus = brokerInfo(broker);
    var guardInfo = guardrailInfo(snapshot);
    setItem("statusbar-ceo", "CORE: " + upper(core.state), tone(core.state));
    setItem("statusbar-genie", "CEO: " + upper(ceo.state), tone(ceo.state));
    var dataStateInfo = getDataStateInfo(data.state);
    var dataText = "DATA: " + dataStateInfo.label;
    if (data.asOf) dataText += " · " + new Date(data.asOf).toLocaleTimeString();
    setItem("statusbar-deep", dataText, dataStateInfo.tone);
    setItem("statusbar-ibkr", brokerStatus.text, brokerStatus.tone);
    setItem("statusbar-guardrails", "MODO: " + mode + " · GUARDRAILS: " + guardInfo.text, worstTone(modeInfo.tone, guardInfo.tone));
    setItem("statusbar-latency", "PIPELINE: " + upper(pipeline.state), tone(pipeline.state));
    var marketStatus = $("live-status");
    if (marketStatus) marketStatus.textContent = "DATA " + dataStateInfo.label;
    var marketTs = $("live-ts");
    if (marketTs) marketTs.textContent = data.asOf || "";
    var label = $("cockpit-connection");
    if (label) {
      /* No safety claim here: the old copy read "MODO SIMULAÇÃO (PAPER)" even
         with the broker offline and paper_trading.active === false. The label
         now reports the broker link as it is, and is only "online" when core is. */
      label.textContent = "CORE " + upper(core.state) + " · " + mode + " MODE · " + upper(broker.provider) + " " + upper(broker.state);
      label.classList.toggle("is-online", String(core.state).toLowerCase() === "online");
    }
    /* broker-status-label / broker-status-btn belong to init.js#updateBrokerStatus,
       which already reports IBKR OFFLINE / PAPER SIM from the same evidence. */
    if (guardrails.passed != null && guardrails.total != null) { var summary = $("guardrails-summary"); if (summary) summary.textContent = guardrails.passed + "/" + guardrails.total; }
  }

  function refresh() { return window.SZ.health && window.SZ.health.check ? window.SZ.health.check() : Promise.resolve(null); }
  function init() { if (window.SZ.subscribe) window.SZ.subscribe("operational-snapshot", render); if (window.SZ.state && window.SZ.state.operationalSnapshot) render(window.SZ.state.operationalSnapshot); }
  window.SZ.statusBar = { refresh: refresh, render: render };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
