/* SuperEzio — Pipeline Progress Bar Renderer */
(function () {
  "use strict";

  var STEPS = [
    "orchestrator", "data", "f51", "pennylab", "experts",
    "neural", "sdca", "rag", "ceo", "explanation",
    "agent", "tool", "blocked", "graph", "scan"
  ];

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
})();
