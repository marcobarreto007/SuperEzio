/* SuperEzio — Health + System Info */
(function () {
  async function check() {
    try {
      const h = await SZ.api.fetchHealth();
      SZ.state.health = h.status === "ok";
    } catch (e) { SZ.state.health = false; }
    const dot = document.getElementById("sys-dot");
    if (dot) {
      dot.className = "status-dot " + (SZ.state.health ? "status-dot--on" : "status-dot--off");
      dot.title = SZ.state.health ? "Connected" : "Disconnected";
    }
    SZ.publish("health", SZ.state.health);
  }

  window.SZ.health = { check };
})();
