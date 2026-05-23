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

  function showDebugCards() {
    return window.SZ_SHOW_DEBUG_CARDS === true;
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
        if (showDebugCards() && SZ.renderExplanation && SZ.renderExplanation.accumulate) {
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
        if (showDebugCards() && SZ.renderPipeline && SZ.renderPipeline.updateStep) {
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
          if (showDebugCards() && SZ.renderF51 && ceoObj) SZ.renderF51(ev, ceoObj);
        })();
        break;

      /* ── SDCA_FIREWALL ── */
      case "SDCA_FIREWALL":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderSDCA && ceoObj) SZ.renderSDCA(ev, ceoObj);
        })();
        break;

      /* ── PENNYLAB_ANALYSIS ── */
      case "PENNYLAB_ANALYSIS":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderPennylab && ceoObj) SZ.renderPennylab(ev, ceoObj);
        })();
        break;

      /* ── CRISIS_MATH ── */
      case "CRISIS_MATH":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderCrisis && ceoObj) SZ.renderCrisis(ev, ceoObj);
        })();
        break;

      /* ── DATA_COLLECTED ── */
      case "DATA_COLLECTED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderDataQuality && ceoObj) SZ.renderDataQuality(ev, ceoObj);
        })();
        break;

      /* ── EXPERT_STARTED ── */
      case "EXPERT_STARTED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "running", ceoObj);
          }
        })();
        break;

      /* ── EXPERT_DONE ── */
      case "EXPERT_DONE":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            var ok = ev.error == null && ev.status !== "error";
            SZ.renderExperts.updateTile(ev.role || "?", ok ? "ok" : "fail", ceoObj);
          }
        })();
        break;

      /* ── EXPERT_SKIPPED ── */
      case "EXPERT_SKIPPED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "skip", ceoObj);
          }
        })();
        break;

      /* ── NEURAL_DECISION ── */
      case "NEURAL_DECISION":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (showDebugCards() && SZ.renderNeural && ceoObj) SZ.renderNeural(ev, ceoObj);
        })();
        break;

      /* ── SCAN_EVENT ── (MRI Registry heartbeat/stage lifecycle) */
      case "SCAN_EVENT":
        (function () {
          if (!SZ.state.scanProgress) SZ.state.scanProgress = {};
          var sp = SZ.state.scanProgress;
          var stage = ev.stage || "?";
          var status = ev.status || "heartbeat";
          sp.currentStage = stage;
          sp.currentStatus = status;
          sp.elapsedMs = ev.elapsed_ms || 0;
          if (ev.counts) {
            sp.done = ev.counts.done || 0;
            sp.total = ev.counts.total || 0;
            sp.errors = ev.counts.errors || 0;
          }
          sp.provider = ev.provider || null;
          if (ev.error) sp.lastError = ev.error;

          /* render scanner status line in chat */
          var ceo = SZ.chat.ensureCEOMessage();
          if (ceo) {
            var existing = ceo.bubble.querySelector(".scanner-progress");
            if (!existing) {
              existing = SZ.dom.el("div", "scanner-progress");
              existing.style.cssText = "font-size:11px;color:#90a4ae;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);margin-bottom:4px;";
              var textNode = ceo.bubble.firstChild;
              if (textNode) ceo.bubble.insertBefore(existing, textNode);
              else ceo.bubble.appendChild(existing);
            }
            var pct = sp.total > 0 ? Math.round(sp.done * 100 / sp.total) : 0;
            var bar = sp.total > 0
              ? " [" + "=".repeat(Math.round(pct/5)) + " ".repeat(20-Math.round(pct/5)) + "] " + pct + "%"
              : "";
            var errText = sp.errors > 0 ? " (" + sp.errors + " err)" : "";
            existing.textContent = "[SCANNER] " + stage + " " + status + bar + errText
              + " | " + (sp.elapsedMs/1000).toFixed(1) + "s";
          }
        })();
        break;

      /* ── SCAN_SUMMARY ── */
      case "SCAN_SUMMARY":
        (function () {
          SZ.state.candidateCount = ev.candidate_count || 0;
          SZ.state.rejectedCount = ev.rejected_count || 0;
          var ceo = SZ.chat.ensureCEOMessage();
          if (ceo) {
            var summary = SZ.dom.el("div", "scan-summary");
            summary.style.cssText = "font-size:12px;color:#66bb6a;padding:6px 8px;background:rgba(102,187,106,0.08);border-radius:4px;margin:4px 0;";
            summary.textContent = "Scan complete: " + SZ.state.candidateCount
              + " candidates, " + SZ.state.rejectedCount + " rejected"
              + (ev.provider_sources_used ? " | sources: " + ev.provider_sources_used.join(", ") : "");
            ceo.bubble.insertBefore(summary, ceo.bubble.firstChild);
          }
        })();
        break;

      /* ── MODEL_MISSING ── */
      case "MODEL_MISSING":
        addWarning("Model missing: " + (ev.model || "unknown"));
        break;

      /* ── ERROR ── */
      case "ERROR":
        if (SZ.state && SZ.state.stream) {
          SZ.state.stream.error = ev.message || ev.error || ev.detail || "Unknown error";
        }
        if (SZ.chat && SZ.chat.finishCEOMessage) SZ.chat.finishCEOMessage();
        break;

      /* ── STREAM_END ── */
      case "STREAM_END":
        /* finalize explanation if streaming */
        if (showDebugCards() && SZ.renderExplanation && SZ.renderExplanation.finalize) {
          var ceoObj2 = SZ.chat.currentCEO;
          if (ceoObj2) SZ.renderExplanation.finalize(ceoObj2);
        }
        SZ.chat.finishCEOMessage();

        if (ev.trace) {
          if (!SZ.state.trace) SZ.state.trace = {};
          Object.assign(SZ.state.trace, ev.trace);
          console.log("Bob Response Trace:", ev.trace);
        }

        var answerText = (SZ.state.stream && SZ.state.stream.answer) || "";
        var cleanAnswer = SZ.chat.stripThink(answerText).trim();
        var hasError = (SZ.state.stream && SZ.state.stream.error) ? true : false;

        if (cleanAnswer === "" || hasError) {
          var currentCEO = SZ.chat.currentCEO;
          if (currentCEO) {
            if (currentCEO.msg && currentCEO.msg.parentNode) {
              currentCEO.msg.parentNode.removeChild(currentCEO.msg);
            }
            SZ.chat.currentCEO = null;
          }
          var route = (SZ.state.stream && SZ.state.stream.route) || "unknown";
          var intent = (SZ.state.stream && SZ.state.stream.intent) || "unknown";
          var reason = (SZ.state.stream && SZ.state.stream.error) || "Empty response returned from backend.";
          addError("Bob failed to produce a valid answer. Route: " + route + ". Classification: " + intent + ". Error: " + reason);
        }
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
