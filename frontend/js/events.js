/* SuperEzio --- Central NDJSON Event Handler */
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

  // Pipeline-progress and explanation cards are dev diagnostics. They are
  // hidden in the clean trader UI unless window.SZ_SHOW_DEBUG_CARDS is set
  // (state.js mirrors SZ.config.showDebugCards, default false in content.js).
  // Verdict cards (F51/SDCA/Neural) always render — they are core output.
  function showDebugCards() {
    return Boolean(window.SZ_SHOW_DEBUG_CARDS);
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

  /* ── Scan UX: rejection reasons + degraded-data warning ── */
  var SCAN_REJECT_LABELS = {
    missing_ticker: "ticker ausente",
    missing_ticker_provenance: "ticker sem origem",
    missing_exchange: "exchange desconhecido",
    missing_price: "preco indisponivel",
    missing_price_provenance: "preco sem origem",
    missing_liquidity: "sem volume/liquidez",
    missing_liquidity_provenance: "liquidez sem origem",
    liquidity_below_minimum: "liquidez abaixo do minimo",
    dollar_volume_below_minimum: "volume em $ abaixo do minimo",
    missing_catalyst: "sem catalisador verificavel",
    missing_catalyst_provenance: "catalisador sem origem",
    missing_short_term_thesis: "sem catalisador/tese de 2 semanas",
    missing_risk: "sem avaliacao de risco",
    missing_risk_provenance: "risco sem origem",
    missing_invalidation: "sem condicao de invalidacao",
    missing_invalidation_provenance: "invalidacao sem origem",
    provider_error: "erro de provedor de dados",
    currency_market_mismatch: "moeda/market incompativel",
    penny_filtered: "penny filtrado",
    otc_filtered: "OTC filtrado",
    exchange_not_td_supported: "bolsa fora do universo TD",
    microcap_filtered: "microcap filtrada",
    price_above_requested_max: "acima do teto pedido",
    quality_gate_failed: "gate de qualidade",
    excluded_previous_recommendation: "ja recomendado",
    unknown: "motivo desconhecido"
  };

  function topRejectionReasons(rejection_summary, limit) {
    if (!rejection_summary) return [];
    var keys = Object.keys(rejection_summary);
    keys.sort(function (a, b) { return (rejection_summary[b] || 0) - (rejection_summary[a] || 0); });
    return keys.slice(0, limit || 3).map(function (k) {
      return (SCAN_REJECT_LABELS[k] || k) + " (" + rejection_summary[k] + ")";
    });
  }

  function renderScanSummary(candidate_count, rejected_count, elapsed_ms, providers) {
    var ceo = SZ.chat.ensureCEOMessage();
    if (!ceo) return;
    var pass = Number(candidate_count) > 0;
    var ls = SZ.state.lastScan || {};
    var summary = ceo.bubble.querySelector(".scan-summary");
    if (!summary) {
      summary = SZ.dom.el("div", "scan-summary");
      ceo.bubble.insertBefore(summary, ceo.bubble.firstChild);
    }
    // The progress line is superseded by the summary — remove it so it
    // never lingers as a stale debug artifact above the final answer.
    var stale = ceo.bubble.querySelector(".scanner-progress");
    if (stale) stale.remove();
    summary.style.cssText = "font-size:12px;color:" + (pass ? "#66bb6a" : "#ffb74d")
      + ";padding:6px 8px;background:" + (pass ? "rgba(102,187,106,0.08)" : "rgba(255,183,77,0.12)")
      + ";border-radius:4px;margin:4px 0;";
    var parts = [
      "Scan " + (pass ? "aprovou " + candidate_count : "concluido sem aprovacao") + ": "
        + candidate_count + " aprovado(s), " + rejected_count + " rejeitado(s)"
    ];
    if (elapsed_ms) parts.push(Math.round(elapsed_ms / 1000) + "s");
    // TD specialization: surface the commission-free count on passing scans.
    var cfree = Number(ls.commission_free_count || 0);
    if (pass && cfree > 0) parts.push("sem comissao TD: " + cfree + " candidato(s)");
    if (!pass) {
      var reasons = topRejectionReasons(ls.rejection_summary);
      if (reasons.length) parts.push("motivos: " + reasons.join(", "));
    }
    if (providers && providers.length) parts.push("fontes: " + providers.join(", "));
    var errs = ls.source_errors || [];
    if (errs.length > 0 || ls.quality === "partial") {
      parts.push("dados degradados" + (errs.length ? " (" + errs.length + " fonte(s) com erro)" : ""));
    }
    summary.textContent = parts.join(" — ");
  }

  /* ==============================================================
   * MAIN EVENT HANDLER
   * ============================================================== */
  function handleEvent(ev) {
    if (!ev || !ev.type) return;
    if (ev.run_id) {
      SZ.state.lastRunId = ev.run_id;
      if (SZ.blamePanel && SZ.blamePanel.setRunId) {
        try { SZ.blamePanel.setRunId(ev.run_id); } catch (_) { /* ignore */ }
      }
    }

    switch (ev.type) {

      /* -- STREAM_START -- */
      case "STREAM_START":
        console.log("[SSE] STREAM_START received, initializing stream");
        SZ.chat.finishCEOMessage();
        SZ.chat.ensureCEOMessage();
        SZ.state.stream = {
          started: Date.now(),
          msgId: ev.msg_id || "",
          runId: ev.run_id || "",
          steps: {},
          ticker: ev.ticker || "",
          answer: ""
        };
        SZ.state.currentCeo = "ceo";
        break;

      /* -- CHART_DATA -- */
      case "CHART_DATA":
        if (ev.chartData) {
          SZ.state.chartData = ev.chartData;
          if (SZ.renderProfile)   SZ.renderProfile();
          if (SZ.renderChart)     SZ.renderChart();
        }
        break;

      /* -- CHUNK -- */
      case "CHUNK":
        if (SZ.chat && SZ.chat.appendChunk) {
          SZ.chat.appendChunk(ev.content || "");
        }
        break;

      /* -- EXPLANATION_CHUNK -- */
      case "EXPLANATION_CHUNK":
        if (showDebugCards() && SZ.renderExplanation && SZ.renderExplanation.accumulate) {
          SZ.renderExplanation.accumulate(ev.content || "");
        }
        break;

      /* -- INTENT_CLASSIFIED -- */
      case "INTENT_CLASSIFIED":
        if (SZ.state.stream) {
          SZ.state.stream.intent = ev.intent;
          SZ.state.stream.route = ev.route;
        }
        break;

      /* -- PIPELINE_STEP -- */
      case "PIPELINE_STEP":
        if (ev.skipped_duplicate) break;
        if (showDebugCards() && SZ.renderPipeline && SZ.renderPipeline.updateStep) {
          var ceoObj = SZ.chat.currentCEO;
          if (ceoObj) {
            SZ.renderPipeline.updateStep(ev.step, ev.status, ceoObj);
          }
        }
        if (ev.step === "graph" && ev.status === "completed" && ev.evidence_run_id) {
          (function () {
            var ceo = SZ.chat && SZ.chat.currentCEO;
            if (!ceo || !ceo.bubble) return;
            var existing = ceo.bubble.querySelector(".evidence-btn");
            if (existing) return;
            var btn = document.createElement("a");
            btn.className = "evidence-btn";
            btn.href = "/evidence/" + ev.evidence_run_id + "/report.html";
            btn.target = "_blank";
            btn.rel = "noopener";
            btn.textContent = "Evidence Report";
            btn.title = "Open auditable evidence report for this analysis";
            btn.style.cssText = "display:inline-block;margin:8px 0;padding:6px 14px;background:#14532d;color:#4ade80;border-radius:6px;text-decoration:none;font-size:0.85em;font-weight:600;";
            ceo.bubble.appendChild(btn);
          })();
        }
        break;

      /* -- F51_VERDICT -- */
      case "F51_VERDICT":
        console.log("[SSE] F51_VERDICT received, rendering card");
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderF51 && ceoObj) SZ.renderF51(ev, ceoObj);
          if (SZ.state) {
            SZ.state.lastF51Verdict = ev;
          }
        })();
        break;

      /* -- SDCA_FIREWALL -- */
      case "SDCA_FIREWALL":
        console.log("[SSE] SDCA_FIREWALL received, rendering card");
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderSDCA && ceoObj) SZ.renderSDCA(ev, ceoObj);
          window.SZ.__sdcaState = ev;
        })();
        break;

      /* -- MATH_REPORT -- */
      case "MATH_REPORT":
        (function () {
          if (SZ.state) SZ.state.lastMathReport = ev;
          var statusEl = document.getElementById("deep-panel-status");
          if (statusEl && ev.ticker) {
            statusEl.textContent = "MATH: " + String(ev.ticker).toUpperCase();
            statusEl.classList.remove("cockpit-panel__status--idle");
          }
          if (ev.generated_at) {
            var latEl = document.getElementById("statusbar-latency");
            if (latEl) latEl.textContent = "Math: " + ev.generated_at.slice(11, 19);
          }
        })();
        break;

      /* -- GUARDRAIL_HUB -- */
      case "GUARDRAIL_HUB":
        console.log("[SSE] GUARDRAIL_HUB received, rendering card");
        (function () {
          if (SZ.state) SZ.state.lastGuardrailHub = ev;
          var summary = ev.summary || {};
          var ok = (summary.decision_counts || {}).ALLOW || 0;
          var total = ev.total_guardrails || 30;
          var blocking = summary.blocking_count || 0;
          var guardEl = document.getElementById("statusbar-guardrails");
          if (guardEl) {
            var cls = "is-ok";
            if (blocking > 0) cls = "is-warn";
            if (blocking > 2) cls = "is-error";
            guardEl.className = "cockpit-statusbar__item " + cls;
            guardEl.textContent = "Guardrails: " + ok + "/" + total + (blocking ? " (" + blocking + " blocking)" : "");
          }
          var latEl = document.getElementById("statusbar-latency");
          if (latEl) latEl.textContent = "Guard: " + new Date().toLocaleTimeString();
        })();
        break;

      /* -- TRINITY_DELIBERATION -- */
      case "TRINITY_DELIBERATION":
        console.log("[SSE] TRINITY_DELIBERATION received, rendering card");
        (function () {
          if (SZ.state) SZ.state.lastTrinity = ev;
          var statusEl = document.getElementById("deep-panel-status");
          if (statusEl) {
            statusEl.textContent = "TRINITY";
            statusEl.classList.remove("cockpit-panel__status--idle");
          }
        })();
        break;

      /* -- PENNYLAB_ANALYSIS -- */
      case "PENNYLAB_ANALYSIS":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderPennylab && ceoObj) SZ.renderPennylab(ev, ceoObj);
        })();
        break;

      /* -- CRISIS_MATH -- */
      case "CRISIS_MATH":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderCrisis && ceoObj) SZ.renderCrisis(ev, ceoObj);
        })();
        break;

      /* -- DATA_COLLECTED -- */
      case "DATA_COLLECTED":
        (function () {
          if (ev.capability === "market_scan" || ev.rejection_summary || ev.source_errors) {
            SZ.state.lastScan = {
              rejection_summary: ev.rejection_summary || null,
              source_errors: ev.source_errors || [],
              quality: ev.quality || null,
              candidates: ev.candidates || 0,
              rejected_count: ev.rejected_count || 0,
              commission_free_count: ev.commission_free_count || 0
            };
            // DATA_COLLECTED can arrive after SCAN_SUMMARY — refresh the
            // summary so rejection reasons show up immediately. Only when the
            // scan actually rejected candidates (ticker_analysis events may
            // also carry rejection data but are covered by the quality card).
            if (ev.rejection_summary && Object.keys(ev.rejection_summary).length > 0) {
              renderScanSummary(
                SZ.state.lastScan.candidates,
                SZ.state.lastScan.rejected_count,
                SZ.state.scanProgress ? SZ.state.scanProgress.elapsedMs : 0,
                ev.providers || null
              );
            }
          }
          var ceoObj = SZ.chat.currentCEO;
          // market_scan DATA_COLLECTED carries rejection stats, not per-source
          // statuses — the generic Data Quality card would render all-unknown
          // tiles (misleading "0/10"). The scan summary covers that case.
          if (ev.capability !== "market_scan" && SZ.renderDataQuality && ceoObj) {
            SZ.renderDataQuality(ev, ceoObj);
          }
        })();
        break;

      /* -- EXPERT_STARTED -- */
      case "EXPERT_STARTED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "running", ceoObj);
          }
        })();
        break;

      /* -- EXPERT_DONE -- */
      case "EXPERT_DONE":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            var ok = ev.error == null && ev.status !== "error";
            SZ.renderExperts.updateTile(ev.role || "?", ok ? "ok" : "fail", ceoObj);
          }
        })();
        break;

      /* -- EXPERT_SKIPPED -- */
      case "EXPERT_SKIPPED":
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderExperts && SZ.renderExperts.updateTile && ceoObj) {
            SZ.renderExperts.updateTile(ev.role || "?", "skip", ceoObj);
          }
        })();
        break;

      /* -- NEURAL_DECISION -- */
      case "NEURAL_DECISION":
        console.log("[SSE] NEURAL_DECISION received, rendering card");
        (function () {
          var ceoObj = SZ.chat.currentCEO;
          if (SZ.renderNeural && ceoObj) SZ.renderNeural(ev, ceoObj);
          window.SZ.__neuralState = ev;
        })();
        break;

      /* -- SCAN_EVENT -- */
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

          var ceo = SZ.chat.ensureCEOMessage();
          if (ceo && !ceo.bubble.querySelector(".scan-summary") && ceo.msg.dataset.done !== "1") {
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

      /* -- SCAN_SUMMARY -- */
      case "SCAN_SUMMARY":
        (function () {
          SZ.state.candidateCount = ev.candidate_count || 0;
          SZ.state.rejectedCount = ev.rejected_count || 0;
          renderScanSummary(
            SZ.state.candidateCount,
            SZ.state.rejectedCount,
            ev.elapsed_ms,
            ev.provider_sources_used || null
          );
        })();
        break;

      /* -- MODEL_MISSING -- */
      case "MODEL_MISSING":
        addWarning("Model missing: " + (ev.model || "unknown"));
        break;

      /* -- ERROR -- */
      case "ERROR":
        if (SZ.state && SZ.state.stream) {
          SZ.state.stream.error = ev.message || ev.error || ev.detail || "Unknown error";
        }
        if (SZ.chat && SZ.chat.finishCEOMessage) SZ.chat.finishCEOMessage();
        break;

      /* -- STREAM_END -- */
      case "STREAM_END":
        console.log("[SSE] STREAM_END received, finalizing stream");
        if (SZ.renderExplanation && SZ.renderExplanation.finalize) {
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
        var entry = {
          ticker:   (SZ.state.stream && SZ.state.stream.ticker) || "",
          prompt:   (SZ.state.stream && SZ.state.stream.answer) || "",
          answer:   "",
          started:  (SZ.state.stream && SZ.state.stream.started) || null,
          finished: Date.now()
        };
        getJournal().push(entry);
        saveJournal();
        var inp = document.getElementById("user-inp");
        var btn = document.getElementById("send-btn");
        if (inp) inp.disabled = false;
        if (btn) btn.disabled = false;
        if (inp) inp.focus();
        break;

      /* -- MANGALA_OPPORTUNITIES -- */
      case "MANGALA_OPPORTUNITIES":
        (function () {
          if (SZ.alerts && SZ.alerts.handleMangalaOpportunity) {
            SZ.alerts.handleMangalaOpportunity(ev);
          }
        })();
        break;

      default:
        break;
    }

    if (SZ.publish) {
      try { SZ.publish("pipeline-event", ev); } catch (e) { console.warn("pipeline publish error:", e); }
    }

    var chat = document.getElementById("chat");
    if (chat) chat.scrollTop = chat.scrollHeight;
  }

  /* ==============================================================
   * SSE PIPELINE STREAM (fallback for real-time events)
   *
   * Creates a persistent fetch() + ReadableStream connection to the
   * backend pipeline event endpoint. Uses fetch() instead of EventSource
   * so we can pass the JWT token in the Authorization header (EventSource
   * only supports query params, which risk leaking the token to logs).
   *
   * If the endpoint is not available (404) the connection falls back to
   * silent polling via /cockpit/summary (handled by cockpit.js).
   *
   * Auto-reconnects with exponential backoff (2s, 4s, 8s ... 30s max).
   * ============================================================== */
  var PIPELINE_SSE_RETRY_DELAYS = [2000, 4000, 8000, 15000, 30000];
  var _pipelineEs = null;
  var _pipelineRetryIdx = 0;
  var _pipelineRetryTimer = null;

  function startPipelineStream(url) {
    stopPipelineStream();
    if (!url) url = "/pipeline/events/stream";

    var auth = window.SZ && window.SZ.auth;
    var token = null;
    if (auth && typeof auth.getValidToken === "function") {
      token = auth.getValidToken();
    }
    if (!token && auth && typeof auth.getToken === "function") {
      token = auth.getToken();
    }

    var headers = { Accept: "application/x-ndjson" };
    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }

    var api = window.SZ && window.SZ.api;
    var base = (api && api.base) || "";
    var absUrl = base + url;
    var ac = new AbortController();
    _pipelineEs = ac;
    _pipelineRetryIdx = 0;

    console.log("[SSE] startPipelineStream connecting to " + absUrl);

    (function connect() {
      if (ac.signal.aborted) return;

      fetch(absUrl, { headers: headers, signal: ac.signal })
        .then(function (resp) {
          if (!resp.ok) {
            console.warn("[SSE] pipeline stream " + resp.status + " - falling back to polling");
            ac.abort();
            _pipelineEs = null;
            return;
          }
          if (!resp.body) {
            console.warn("[SSE] pipeline stream has no body - fallback to polling");
            ac.abort();
            _pipelineEs = null;
            return;
          }

          console.log("[SSE] pipeline stream connected");
          _pipelineRetryIdx = 0;

          var reader = resp.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";

          function pump() {
            if (ac.signal.aborted) return;
            reader.read().then(function (result) {
              if (result.done) {
                console.log("[SSE] pipeline stream ended (done=true)");
                scheduleReconnect(ac);
                return;
              }
              buffer += decoder.decode(result.value, { stream: true });

              var lines = buffer.split("\n");
              buffer = lines.pop();

              for (var i = 0; i < lines.length; i++) {
                var line = lines[i].trim();
                if (!line) continue;
                var ev = null;
                try {
                  ev = JSON.parse(line);
                } catch (parseErr) {
                  if (line.indexOf("data:") === 0) {
                    try {
                      ev = JSON.parse(line.slice(5).trim());
                    } catch (_) { /* skip malformed */ }
                  }
                  if (!ev) {
                    console.warn("[SSE] parse error (skipping line):", parseErr, line);
                    continue;
                  }
                }
                try {
                  if (window.SZ.handleEvent) SZ.handleEvent(ev);
                } catch (handlerErr) {
                  console.warn("[SSE] handleEvent error:", handlerErr, ev);
                }
              }

              if (typeof window.scheduler !== "undefined" && typeof window.scheduler.yield === "function") {
                window.scheduler.yield().then(pump);
              } else {
                setTimeout(pump, 0);
              }
            }).catch(function (err) {
              if (err.name === "AbortError") return;
              console.warn("[SSE] read error:", err);
              scheduleReconnect(ac);
            });
          }

          pump();
        })
        .catch(function (err) {
          if (err.name === "AbortError") return;
          console.warn("[SSE] connection error:", err);
          scheduleReconnect(ac);
        });
    })();
  }

  function scheduleReconnect(ac) {
    if (ac.signal.aborted) return;
    if (_pipelineRetryIdx >= PIPELINE_SSE_RETRY_DELAYS.length) {
      console.warn("[SSE] max reconnect attempts reached - stopping pipeline stream");
      return;
    }
    var delay = PIPELINE_SSE_RETRY_DELAYS[_pipelineRetryIdx];
    _pipelineRetryIdx++;
    console.log("[SSE] reconnecting in " + delay + "ms (attempt " + _pipelineRetryIdx + ")");
    _pipelineRetryTimer = setTimeout(function () {
      if (_pipelineEs === ac) {
        startPipelineStream();
      }
    }, delay);
  }

  function stopPipelineStream() {
    if (_pipelineRetryTimer) {
      clearTimeout(_pipelineRetryTimer);
      _pipelineRetryTimer = null;
    }
    if (_pipelineEs) {
      try { _pipelineEs.abort(); } catch (_) { /* ignore */ }
      _pipelineEs = null;
    }
    _pipelineRetryIdx = 0;
  }

  window.SZ = window.SZ || {};
  window.SZ.handleEvent = handleEvent;
  window.SZ.startPipelineStream = startPipelineStream;
  window.SZ.stopPipelineStream = stopPipelineStream;
})();
