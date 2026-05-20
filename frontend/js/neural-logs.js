/* SuperEzio — Neural Logs SSE Panel */
(function () {
  let es = null;
  const MAX_LINES = 200;

  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  function start() {
    stop();
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    pc.innerHTML = '<div class="log-terminal" id="log-terminal"></div>';
    const term = document.getElementById("log-terminal");

    es = new EventSource(SZ.api.neuralLogsURL());

    es.onmessage = function (evt) {
      const raw = evt.data || "";
      const text = raw.startsWith("NEURAL_LOG: ") ? raw.slice(12) : raw;
      try {
        const obj = JSON.parse(text);
        appendLine(term, obj);
      } catch {
        appendRaw(term, raw);
      }
    };

    es.onerror = function () {
      appendRaw(term, "[SSE connection error — retrying...]");
    };
  }

  function appendLine(term, obj) {
    const level = (obj.phase || "").toLowerCase();
    const cls = level.includes("error") ? "log-line--error" : level.includes("warn") ? "log-line--warn" : level.includes("info") ? "log-line--info" : "";
    const ts = obj.timestamp ? new Date(obj.timestamp).toLocaleTimeString() : "";
    const msg = [ts, obj.event, obj.message].filter(Boolean).join(" | ");
    const div = document.createElement("div");
    div.className = "log-line " + cls;
    div.textContent = msg;
    trimAndAppend(term, div);
  }

  function appendRaw(term, text) {
    const div = document.createElement("div");
    div.className = "log-line";
    div.textContent = text;
    trimAndAppend(term, div);
  }

  function trimAndAppend(term, div) {
    term.appendChild(div);
    while (term.children.length > MAX_LINES) term.removeChild(term.firstChild);
    term.scrollTop = term.scrollHeight;
  }

  function stop() {
    if (es) { es.close(); es = null; }
  }

  function showPanel() {
    if (es) { stop(); return; }
    start();
  }

  window.SZ.neuralLogs = { showPanel, stop };
})();
