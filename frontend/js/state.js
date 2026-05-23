/* SuperEzio — State + Event Bus */
(function () {
  const state = {
    health: false,
    healthDetails: null,
    ticker: "",
    chartData: null,
    portfolio: {},
    stream: null,
    busy: false,
    live: { enabled: false, es: null, connected: false },
    panels: {},     // which panel is open
    journal: [],
    metrics: null,
    manifest: null,
    capabilities: null,
    neuralLogs: [],
    scanProgress: null,         // current SCAN_EVENT heartbeat
    candidateCount: 0,
    rejectedCount: 0,
  };

  const listeners = {};

  function subscribe(key, fn) {
    (listeners[key] = listeners[key] || []).push(fn);
  }

  function publish(key, data) {
    (listeners[key] || []).forEach(fn => { try { fn(data); } catch (e) { console.error("bus error:", key, e); } });
  }

  window.SZ = window.SZ || {};
  window.SZ.state = state;
  window.SZ.subscribe = subscribe;
  window.SZ.publish = publish;
})();
