/* SuperEzio CockpitShell — Central Hub v2 */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function setText(id, value) { var el = $(id); if (el) el.textContent = value; }
  function mark(el, state) {
    if (!el) return;
    el.classList.remove("is-ok", "is-error", "is-warn");
    if (state) el.classList.add(state);
  }

  function setConnection(online) {
    var dot = $("sys-dot");
    var label = $("cockpit-connection");
    if (dot) {
      dot.classList.toggle("status-dot--on", Boolean(online));
      dot.classList.toggle("status-dot--off", !online);
      dot.title = online ? "CONECTADO" : "DESCONECTADO";
    }
    if (label) {
      label.classList.toggle("is-online", Boolean(online));
      label.textContent = online ? "CONECTADO" : "DESCONECTADO";
    }
  }

  // ── Status Bar (all 6 indicators) ──
  function updateStatusBar(data) {
    if (!data) return;
    // Handle nested objects from backend: status.genie = {status: "online", ...}
    var ceoOk = (typeof data.ceo === "object" ? data.ceo.status : data.ceo) === "online";
    var genieStatus = typeof data.genie === "object" ? data.genie.status : data.genie;
    var deepStatus = typeof data.deep === "object" ? data.deep.status : data.deep;
    var ibkrStatus = typeof data.ibkr === "object" ? data.ibkr.status : data.ibkr;
    var genieOk = genieStatus === "online";
    var deepOk = deepStatus === "online" || deepStatus === "degraded";
    var ibkrOk = ibkrStatus === "online";

    mark($("statusbar-ceo"), ceoOk ? "is-ok" : "is-error");
    setText("statusbar-ceo", "CEO: " + (ceoOk ? "ONLINE" : "OFFLINE"));

    mark($("statusbar-genie"), genieOk ? "is-ok" : "is-error");
    setText("statusbar-genie", "Genie: " + (genieOk ? "online" : "OFFLINE"));

    mark($("statusbar-deep"), deepOk ? "is-ok" : "is-error");
    setText("statusbar-deep", "Deep: " + (deepStatus || "OFFLINE"));

    mark($("statusbar-ibkr"), ibkrOk ? "is-ok" : "is-warn");
    setText("statusbar-ibkr", "IBKR: " + (ibkrOk ? (typeof data.ibkr === "object" ? (data.ibkr.equity || "Paper") : "Paper") : "OFFLINE"));

    var guards = data.guardrails || {};
    var guardsOk = guards.ok || data.guards_ok || 30;
    var guardsTotal = guards.total || data.guards_total || 30;
    mark($("statusbar-guardrails"), guardsOk >= guardsTotal ? "is-ok" : "is-warn");
    setText("statusbar-guardrails", "Guardrails: " + guardsOk + "/" + guardsTotal);

    mark($("statusbar-latency"), "is-warn");
    setText("statusbar-latency", "Last run: --");
  }

  // ── Populators — feed data from /cockpit/summary into each panel state ──
  function feedGenie(data) {
    if (!data || !window.SZ.geniePanel) return;
    if (window.SZ.geniePanel.renderFromCockpit) {
      window.SZ.geniePanel.renderFromCockpit(data);
    }
  }

  function feedDeep(data) {
    if (!data) return;
    var state = window.SZ.state.deep = window.SZ.state.deep || {};
    if (data.last_math) state.math = data.last_math;
    if (data.last_experts) {
      state.experts = {};
      (data.last_experts || []).forEach(function (ex) {
        state.experts[ex.role || ex.expert] = ex;
      });
    }
    if (data.last_trinity) state.trinity = data.last_trinity;
    if (window.SZ.deepPanel && window.SZ.deepPanel.render) window.SZ.deepPanel.render();
  }

  function feedBob(data) {
    if (!data) return;
    var state = window.SZ.state.bobPanel = window.SZ.state.bobPanel || { steps: {} };
    if (data.last_decision) state.lastCockpitDecision = data.last_decision;
    if (data.guardrails) state.guardrailCockpit = data.guardrails;
    if (data.portfolio) state.portfolio = data.portfolio;
    if (window.SZ.bobPanel && window.SZ.bobPanel.render) window.SZ.bobPanel.render();
  }

  // ── Main Poll — pulls /cockpit/summary and distributes to all panels ──
  async function refreshAll() {
    var online = false;
    try {
      var health = await window.SZ.api.fetchHealth();
      online = health && health.status === "ok";
    } catch (e) { online = false; }
    setConnection(online);

    if (!online) {
      updateStatusBar({ ceo: "offline", genie: "offline", deep: "offline", ibkr: "offline" });
      return;
    }

    try {
      var s = await window.SZ.api.fetchCockpitSummary();
      if (!s) return;

      // Backend returns status as nested objects: {ceo: "online", genie: {status: "online"}, ...}
      // Pass raw status through — updateStatusBar handles both flat and nested
      updateStatusBar(s.status || {});

      feedGenie(s.genie);
      feedDeep(s.deep);
      feedBob(s.bob);
    } catch (e) {
      // cockpit summary unreachable — panels keep last known state
    }
  }

  function init() {
    refreshAll();
    window.setInterval(refreshAll, 10000);
  }

  window.SZ = window.SZ || {};
  window.SZ.cockpit = Object.assign(window.SZ.cockpit || {}, {
    refreshAll: refreshAll,
    updateStatusBar: updateStatusBar,
    feedDeep: feedDeep,
    feedGenie: feedGenie,
    feedBob: feedBob,
  });

  document.addEventListener("DOMContentLoaded", init);
})();
