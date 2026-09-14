/* SuperEzio — Pipeline Progress Bar Renderer */
(function () {
  "use strict";

  var STEPS = [
    "orchestrator", "data", "f51", "pennylab", "experts",
    "neural", "sdca", "rag", "ceo", "explanation",
    "agent", "tool", "blocked", "graph", "scan"
  ];

  /* ==============================================================
   * Card freshness stamps — shared helper for every render-*.js card.
   * --------------------------------------------------------------
   * Every card must say WHEN its content is from. Two clocks, never
   * mixed, and the label always says which one you are looking at:
   *
   *   source "data"    — the payload carried a real producer timestamp
   *                      (as_of / generated_at / ...). The stamp shows
   *                      the age of THAT timestamp.
   *   source "receipt" — the payload carried none. The stamp shows when
   *                      the frontend received the event. That is NOT
   *                      the time of the data, and the tooltip says so.
   *
   * Why these thresholds:
   *   2 min  -> amber. The events arrive over a live order-book stream,
   *            so a healthy card is re-stamped within seconds of its
   *            data being produced. Past ~2 min it is no longer "from
   *            this run" — a full run is minutes, not tens of minutes.
   *   10 min -> red. frontend/js/health.js:24 only downgrades the
   *            footer to STALE after 15 min, over data already held in
   *            memory. A card-level stamp that fires later than the
   *            footer adds nothing, so the card goes red at 10 min and
   *            gives the operator a 5 min head start on the outage.
   *
   * A card whose backend timestamp is a bar/market time (NEURAL as_of)
   * turns red straight away. That is correct, not a false alarm: the
   * underlying data really is that old, however recently it was drawn.
   * ============================================================== */

  var STAMP_WARN_MS  = 2 * 60 * 1000;
  var STAMP_STALE_MS = 10 * 60 * 1000;
  var STAMP_TICK_MS  = 10000;

  /* Producer-side timestamp keys actually emitted in this codebase and
   * the ones a future emitter would plausibly use. Deliberately NOT
   * included: bare "ts" / "time" (too often a bar label or a number,
   * never a wall clock here) — a false positive would stamp a card with
   * a time the backend never sent. */
  var STAMP_KEYS = [
    "as_of", "generated_at", "fetched_at", "updated_at", "created_at",
    "last_update", "timestamp", "scanned_at", "verified_at"
  ];

  var _stamps = [];
  var _tick = null;

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function parseTime(v) {
    if (v == null) return null;
    if (typeof v === "number") {
      if (!isFinite(v) || v <= 0) return null;
      return v < 1e11 ? v * 1000 : v;   // seconds vs milliseconds
    }
    if (typeof v === "string") {
      var s = v.trim();
      if (!s) return null;
      var t = Date.parse(s);
      return isFinite(t) ? t : null;
    }
    return null;
  }

  /* Bounded walk for the first producer timestamp in the payload.
   * Own keys are checked before descending, so a top-level `as_of`
   * always wins over a nested one. */
  function scanForTime(node, depth, seen) {
    if (!node || typeof node !== "object" || depth > 3 || seen.length > 40) return null;
    if (seen.indexOf(node) >= 0) return null;
    seen.push(node);

    var i, key;
    if (!Array.isArray(node)) {
      for (i = 0; i < STAMP_KEYS.length; i++) {
        key = STAMP_KEYS[i];
        if (Object.prototype.hasOwnProperty.call(node, key)) {
          var t = parseTime(node[key]);
          if (t != null) return { ms: t, key: key };
        }
      }
    }
    var values = Array.isArray(node)
      ? node
      : Object.keys(node).map(function (k) { return node[k]; });
    for (i = 0; i < values.length; i++) {
      var hit = scanForTime(values[i], depth + 1, seen);
      if (hit) return hit;
    }
    return null;
  }

  function findDataTime(ev) {
    if (!ev || typeof ev !== "object") return null;
    return scanForTime(ev, 0, []);
  }

  function relText(ageMs) {
    var s = Math.floor(ageMs / 1000);
    if (s < 10) return "agora";
    if (s < 60) return "há " + s + "s";
    var m = Math.floor(s / 60);
    if (m < 60) return "há " + m + "m";
    var h = Math.floor(m / 60);
    if (h < 24) return "há " + h + "h" + (m % 60 ? pad2(m % 60) : "");
    return "há " + Math.floor(h / 24) + "d";
  }

  function absText(ms) {
    var d = new Date(ms);
    var now = new Date();
    if (d.toDateString() !== now.toDateString()) {
      return pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) + " " +
             pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    }
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
  }

  function ageColor(ageMs) {
    if (ageMs >= STAMP_STALE_MS) return "var(--red)";
    if (ageMs >= STAMP_WARN_MS) return "var(--amber)";
    return "var(--green)";
  }

  /* Paint never checks isConnected: cards are built detached and only
   * inserted into the bubble afterwards, so a connectedness guard here
   * would silently leave every stamp blank. Pruning happens in
   * refresh(), where "detached" really does mean "card was closed". */
  function paint(entry) {
    var node = entry.node;
    if (!node) return;

    var age = Date.now() - entry.ts;
    var isData = entry.source === "data";
    var text = (isData ? "dado " : "recebido ") + relText(age) + " · " + absText(entry.ts);
    if (node.textContent !== text) node.textContent = text;

    var color = ageColor(age);
    if (entry.color !== color) {
      node.style.color = color;
      entry.color = color;
    }
  }

  function refresh() {
    var alive = [];
    for (var i = 0; i < _stamps.length; i++) {
      var entry = _stamps[i];
      if (!entry.node || !entry.node.isConnected) continue;  // card closed
      paint(entry);
      alive.push(entry);
    }
    _stamps = alive;
    if (!_stamps.length && _tick) {
      window.clearInterval(_tick);
      _tick = null;
    }
  }

  function register(node, ts, source) {
    for (var i = 0; i < _stamps.length; i++) {
      if (_stamps[i].node === node) {
        _stamps[i].ts = ts;
        _stamps[i].source = source;
        _stamps[i].color = null;
        return _stamps[i];
      }
    }
    var entry = { node: node, ts: ts, source: source, color: null };
    _stamps.push(entry);
    if (!_tick) _tick = window.setInterval(refresh, STAMP_TICK_MS);
    return entry;
  }

  /* attach(cardEl, { time, key, label })
   *   time  — ms epoch of the producer timestamp, or null/absent for
   *           "no backend timestamp: use receipt time".
   *   key   — the backend field the timestamp came from (for the tooltip).
   *   label — human name of the source of the event. */
  function attach(cardEl, opts) {
    if (!cardEl) return null;
    opts = opts || {};

    var ts = parseTime(opts.time);
    var source = ts != null ? "data" : "receipt";
    if (ts == null) ts = Date.now();

    var hdr = cardEl.querySelector(".card-hdr") || cardEl;
    var node = hdr.querySelector(".sz-stamp");
    if (!node) {
      node = SZ.dom.el("span", "sz-stamp");
      var closeBtn = hdr.querySelector(".card-close");
      if (closeBtn) hdr.insertBefore(node, closeBtn);
      else hdr.appendChild(node);
    }

    // Solid left rule = real backend timestamp. Dashed = receipt time
    // only. Tells the two clocks apart without reading the words.
    node.style.cssText = [
      "margin-left:8px",
      "flex:0 0 auto",
      "white-space:nowrap",
      "font:700 10px/1.6 var(--font-mono)",
      "letter-spacing:0.02em",
      "padding:2px 7px",
      "border-radius:4px",
      "background:rgba(255,255,255,0.03)",
      "border-left:2px " + (source === "data" ? "solid" : "dashed") + " currentColor"
    ].join(";");

    var abs = new Date(ts).toLocaleString();
    node.title = source === "data"
      ? "Timestamp do dado enviado pelo backend (\"" + (opts.key || "?") + "\" = " + abs +
        "). O carimbo mostra a idade DESSE dado" +
        (opts.label ? ", não o momento em que o card foi pintado (" + opts.label + ")." : ".")
      : "O backend NÃO envia timestamp para este card. A hora mostrada (" + abs +
        ") é quando o frontend recebeu o evento — NÃO é a hora do dado. " +
        "Se ela envelhecer, o backend parou de responder.";

    paint(register(node, ts, source));
    return node;
  }

  /* stampCard(cardEl, ev, label) — auto-pick the backend timestamp out
   * of the raw event; fall back to receipt time when there is none. */
  function stampCard(cardEl, ev, label) {
    var hit = findDataTime(ev);
    return attach(cardEl, {
      time: hit ? hit.ms : null,
      key: hit ? hit.key : null,
      label: label || null
    });
  }

  var stepMap = {
    orchestrator_primary: "orchestrator",
    data_collection: "data",
    data: "data",
    professional_collector: "data",
    f51_verdict: "f51",
    f51_engine: "f51",
    pennylab: "pennylab",
    penny_lab: "pennylab",
    run_expert: "experts",
    expert_analysis: "experts",
    neural_decision: "neural",
    sdca_firewall: "sdca",
    rag_forensics: "rag",
    ceo_primary: "ceo",
    llm: "ceo",
    explanation: "explanation",
    agent: "agent",
    tool_executor: "tool",
    respond_blocked: "blocked",
    graph: "graph",
    market_scan_answer: "scan"
  };

  function resolveStep(raw) {
    if (!raw) return null;
    var key = String(raw).toLowerCase().trim();
    if (stepMap[key]) return stepMap[key];
    if (STEPS.indexOf(key) >= 0) return key;
    return null;
  }

  function renderBar(ceo) {
    var container = SZ.dom.el("div", "pipeline-bar");
    container.setAttribute("data-sz-pipeline", "1");

    var track = SZ.dom.el("div", "pipeline-track");

    STEPS.forEach(function (name) {
      var step = SZ.dom.el("div", "pipeline-step pipeline-step--pending");
      step.setAttribute("data-step", name);
      step.setAttribute("title", name);

      var icon = SZ.dom.el("span", "pipeline-step__icon");
      icon.textContent = "●";
      step.appendChild(icon);

      var label = SZ.dom.el("span", "pipeline-step__label");
      label.textContent = name;
      step.appendChild(label);

      track.appendChild(step);
    });

    container.appendChild(track);

    // Insert into CEO bubble before any cards
    var bubble = ceo.bubble;
    var firstCard = bubble.querySelector(".card");
    if (firstCard) {
      bubble.insertBefore(container, firstCard);
    } else {
      bubble.appendChild(container);
    }

    return container;
  }

  function updateStep(step, status, ceo) {
    var resolved = resolveStep(step);
    if (!resolved) return;

    if (window.SZ && window.SZ.state) {
      window.SZ.state.activePipelineNode = status === "running" ? resolved : null;
      if (status === "running") window.SZ.state.busy = true;
      if (status === "fail") window.SZ.state.pipelineError = true;
      if (status === "done" && resolved === "explanation") window.SZ.state.busy = false;
      if (window.SZ.health && window.SZ.health.buildSnapshot) {
        var snapshot = window.SZ.health.buildSnapshot(window.SZ.state.healthDetails);
        window.SZ.state.operationalSnapshot = snapshot;
        window.SZ.publish("operational-snapshot", snapshot);
      }
    }

    var bar = ceo.bubble.querySelector("[data-sz-pipeline]");
    if (!bar) bar = renderBar(ceo);

    var el = bar.querySelector('[data-step="' + resolved + '"]');
    if (!el) return;

    el.classList.remove(
      "pipeline-step--pending",
      "pipeline-step--running",
      "pipeline-step--done",
      "pipeline-step--fail"
    );

    var statusClass = "pipeline-step--" + (status || "pending");
    el.classList.add(statusClass);

    var icon = el.querySelector(".pipeline-step__icon");
    if (icon) {
      if (status === "done") icon.textContent = "✓";
      else if (status === "fail") icon.textContent = "✗";
      else if (status === "running") icon.textContent = "▶";
      else icon.textContent = "●";
    }

    return el;
  }

  window.SZ.renderPipeline = {
    renderBar: renderBar,
    updateStep: updateStep,
    STEPS: STEPS,
    stepMap: stepMap
  };

  /* Shared card-freshness stamps — every render-*.js card calls this. */
  window.SZ.stamp = {
    card: stampCard,
    attach: attach,
    refresh: refresh,
    findDataTime: findDataTime,
    WARN_MS: STAMP_WARN_MS,
    STALE_MS: STAMP_STALE_MS
  };
})();
