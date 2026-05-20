/* SuperEzio — Central NDJSON Event Handler */
(function () {
  "use strict";

  var STEPS = [
    "orchestrator","data","f51","pennylab","experts",
    "neural","sdca","rag","ceo","explanation"
  ];

  function esc(s) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
  }

  function getCeoBubble() {
    if (!SZ.chat || !SZ.chat.currentCEO) return null;
    return SZ.chat.currentCEO.bubble || null;
  }

  function getJournal() {
    if (!SZ.state) SZ.state = {};
    if (!SZ.state.journal) SZ.state.journal = [];
    return SZ.state.journal;
  }

  function saveJournal() {
    try { localStorage.setItem("sz_journal", JSON.stringify(getJournal())); } catch (e) { /* ignore */ }
  }

  function addWarning(msg) {
    var bubble = getCeoBubble();
    if (!bubble) return;
    var div = document.createElement("div");
    div.style.cssText = "color:#ff9800;font-size:12px;padding:4px 8px;";
    div.textContent = msg;
    bubble.appendChild(div);
  }

  function addError(msg) {
    var chat = document.getElementById("chat");
    if (!chat) return;
    var div = document.createElement("div");
    div.style.cssText = "color:#ff1744;padding:8px 12px;background:rgba(255,23,68,0.08);border-radius:6px;margin:4px 0;font-size:13px;";
    div.textContent = msg;
    chat.appendChild(div);
  }

  /* ═══════════════════════════════════════════════════════════════
   * MAIN EVENT HANDLER
   * ═══════════════════════════════════════════════════════════════ */
  function handleEvent(ev) {
    if (!ev || !ev.type) return;

    switch (ev.type) {

      /* ── STREAM_START ── */
      case "STREAM_START":
        SZ.chat.finishCEOMessage();
        SZ.chat.ensureCEOMessage();
        SZ.state.stream = {
          started: Date.now(),
          steps: {},
          ticker: ev.ticker || "",
          answer: ""
        };
        SZ.state.currentCeo = "ceo";
        break;

      /* ── CHART_DATA ── */
      case "CHART_DATA":
        if (ev.chartData) {
          SZ.state.chartData = ev.chartData;
          if (SZ.renderProfile)   SZ.renderProfile();
          if (SZ.renderChart)     SZ.renderChart();
        }
        break;

      /* ── CHUNK ── */
      case "CHUNK":
        if (SZ.chat && SZ.chat.appendChunk) {
          SZ.chat.appendChunk(ev.content || "");
        }
        break;

      /* ── EXPLANATION_CHUNK ── */
      case "EXPLANATION_CHUNK":
        if (SZ.renderExplanation && SZ.renderExplanation.accumulate) {
          SZ.renderExplanation.accumulate(ev.content || "");
        }
        break;

      /* ── INTENT_CLASSIFIED ── */
      case "INTENT_CLASSIFIED":
        /* informational only — could add chips later */
        if (SZ.state.stream) {
          SZ.state.stream.intent = ev.intent;
          SZ.state.stream.route = ev.route;
        }
        break;

      /* ── PIPELINE_STEP ── */
      case "PIPELINE_STEP":
        if (ev.skipped_duplicate) break;
        if (SZ.renderPipeline && SZ.renderPipeline.updateStep) {
          var ceoObj = SZ.chat.currentCEO;
          if (ceoObj) {
            SZ.renderPipeline.updateStep(ev.step, ev.status, ceoObj);
          }
        }
        break;

      /* ── F51_VERDICT ── */
      case "F51_VERDICT":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderF51 && ceoObj) SZ.renderF51(ev, ceoObj);
        })();
        break;

      /* ── SDCA_FIREWALL ── */
      case "SDCA_FIREWALL":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderSDCA && ceoObj) SZ.renderSDCA(ev, ceoObj);
        })();
        break;

      /* ── PENNYLAB_ANALYSIS ── */
      case "PENNYLAB_ANALYSIS":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderPennylab && ceoObj) SZ.renderPennylab(ev, ceoObj);
        })();
        break;

      /* ── CRISIS_MATH ── */
      case "CRISIS_MATH":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderCrisis && ceoObj) SZ.renderCrisis(ev, ceoObj);
        })();
        break;

      /* ── DATA_COLLECTED ── */
      case "DATA_COLLECTED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderDataQuality && ceoObj) SZ.renderDataQuality(ev, ceoObj);
        })();
        break;

      /* ── EXPERT_STARTED ── */
      case "EXPERT_STARTED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "running", ceoObj);
          }
        })();
        break;

      /* ── EXPERT_DONE ── */
      case "EXPERT_DONE":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            var ok = ev.error == null && ev.status !== "error";
            SZ.renderExperts.updateTile(ev.role || "?", ok ? "ok" : "fail", ceoObj);
          }
        })();
        break;

      /* ── EXPERT_SKIPPED ── */
      case "EXPERT_SKIPPED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "skip", ceoObj);
          }
        })();
        break;

      /* ── NEURAL_DECISION ── */
      case "NEURAL_DECISION":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderNeural && ceoObj) SZ.renderNeural(ev, ceoObj);
        })();
        break;

      /* ── MODEL_MISSING ── */
      case "MODEL_MISSING":
        addWarning("Model missing: " + (ev.model || "unknown"));
        break;

      /* ── ERROR ── */
      case "ERROR":
        addError(ev.message || ev.error || "Unknown error");
        break;

      /* ── STREAM_END ── */
      case "STREAM_END":
        /* finalize explanation if streaming */
        if (SZ.renderExplanation && SZ.renderExplanation.finalize) {
          var ceoObj2 = SZ.chat.currentCEO;
          if (ceoObj2) SZ.renderExplanation.finalize(ceoObj2);
        }
        SZ.chat.finishCEOMessage();
        /* save to journal */
        var entry = {
          ticker:   (SZ.state.stream && SZ.state.stream.ticker) || "",
          prompt:   (SZ.state.stream && SZ.state.stream.answer) || "",
          answer:   "",
          started:  (SZ.state.stream && SZ.state.stream.started) || null,
          finished: Date.now()
        };
        getJournal().push(entry);
        saveJournal();
        /* re-enable input */
        var inp = document.getElementById("user-inp");
        var btn = document.getElementById("send-btn");
        if (inp) inp.disabled = false;
        if (btn) btn.disabled = false;
        if (inp) inp.focus();
        break;

      default:
        break;
    }

    /* scroll chat */
    var chat = document.getElementById("chat");
    if (chat) chat.scrollTop = chat.scrollHeight;
  }

  window.SZ = window.SZ || {};
  window.SZ.handleEvent = handleEvent;
})();
