/* SuperEzio CockpitShell */
(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function setText(id, value) {
    var el = $(id);
    if (el) el.textContent = value;
  }

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
    mark($("statusbar-ceo"), online ? "is-ok" : "is-error");
    setText("statusbar-ceo", online ? "CEO: ONLINE" : "CEO: OFFLINE");
  }

  async function probeConnection() {
    try {
      var health = await window.SZ.api.fetchHealth();
      var online = health && health.status === "ok";
      setConnection(online);
      return online;
    } catch (e) {
      setConnection(false);
      return false;
    }
  }

  function init() {
    probeConnection();
    window.setInterval(probeConnection, 15000);
  }

  window.SZ = window.SZ || {};
  window.SZ.cockpit = Object.assign(window.SZ.cockpit || {}, {
    initShell: init,
    probeConnection: probeConnection,
    setConnection: setConnection,
  });

  document.addEventListener("DOMContentLoaded", init);
})();
