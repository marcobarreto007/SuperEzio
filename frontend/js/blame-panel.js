/* SuperEzio Blame Report Panel */
(function () {
  "use strict";

  var lastAutoRunId = "";
  var loadingRunId = "";

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function setBody(html) {
    var body = byId("blame-report-body");
    if (body) body.innerHTML = html;
  }

  function setRunId(runId) {
    runId = String(runId || "").trim();
    if (!runId) return;
    var input = byId("blame-run-id");
    if (!input) return;
    if (!input.value || input.value === lastAutoRunId) {
      input.value = runId;
      lastAutoRunId = runId;
    }
  }

  function toneClass(value) {
    var text = String(value || "").toLowerCase();
    if (text.indexOf("error") >= 0 || text.indexOf("fail") >= 0 || text.indexOf("block") >= 0) return "is-bad";
    if (text.indexOf("skip") >= 0 || text.indexOf("warn") >= 0) return "is-warn";
    return "is-good";
  }

  function renderSummary(summary) {
    summary = summary || {};
    var items = [
      ["Events", summary.total_events],
      ["Completed", summary.completed_nodes],
      ["Skipped", summary.skipped_nodes],
      ["Errors", summary.error_nodes],
      ["Blockers", summary.blockers],
    ];
    return '<div class="blame-summary-grid">' + items.map(function (item) {
      return '<div><span>' + esc(item[0]) + '</span><strong>' + esc(item[1] == null ? 0 : item[1]) + '</strong></div>';
    }).join("") + '</div>';
  }

  function renderList(title, rows, emptyText, formatter) {
    rows = Array.isArray(rows) ? rows : [];
    if (!rows.length) {
      return '<section class="blame-section"><div class="cockpit-section__title">' + esc(title) + '</div><div class="cockpit-empty">' + esc(emptyText) + '</div></section>';
    }
    return [
      '<section class="blame-section">',
      '<div class="cockpit-section__title">' + esc(title) + '</div>',
      '<div class="blame-list">',
      rows.slice(0, 8).map(formatter).join(""),
      '</div>',
      '</section>',
    ].join("");
  }

  function renderEntry(entry, index) {
    entry = entry || {};
    var label = entry.node || entry.agent || entry.event_type || entry.type || ("event_" + (index + 1));
    var status = entry.status || entry.verdict || entry.result || "event";
    var when = entry.timestamp || entry.created_at || "";
    var payload = JSON.stringify(entry, null, 2);
    return [
      '<details class="blame-entry">',
      '<summary><span>' + esc(label) + '</span><strong class="' + toneClass(status) + '">' + esc(status) + '</strong></summary>',
      '<div class="blame-entry__time">' + esc(when) + '</div>',
      '<pre>' + esc(payload) + '</pre>',
      '</details>',
    ].join("");
  }

  function renderReport(report) {
    report = report || {};
    var blockers = Array.isArray(report.blockers) ? report.blockers : [];
    var slowest = Array.isArray(report.slowest_nodes) ? report.slowest_nodes : [];
    var entries = Array.isArray(report.entries) ? report.entries : [];
    var html = [
      '<div class="blame-run-line"><span>Run</span><strong>' + esc(report.run_id || "") + '</strong></div>',
      renderSummary(report.summary || {}),
      renderList("Blockers", blockers, "No blockers recorded.", function (row) {
        var node = row.node || row.agent || row.step || "blocker";
        var reason = row.reason || row.message || row.error || JSON.stringify(row);
        return '<div class="blame-row is-bad"><strong>' + esc(node) + '</strong><span>' + esc(reason) + '</span></div>';
      }),
      renderList("Slowest Nodes", slowest, "No latency data recorded.", function (row) {
        var node = row.node || row.agent || row.step || "node";
        var ms = row.duration_ms || row.elapsed_ms || row.ms || row.latency_ms || "--";
        return '<div class="blame-row"><strong>' + esc(node) + '</strong><span>' + esc(ms) + ' ms</span></div>';
      }),
      renderList("Agent Stats", Object.entries(report.agent_stats || {}), "No agent stats recorded.", function (pair) {
        return '<div class="blame-row"><strong>' + esc(pair[0]) + '</strong><span>' + esc(JSON.stringify(pair[1])) + '</span></div>';
      }),
      '<section class="blame-section"><div class="cockpit-section__title">Trace Events</div>',
      entries.length ? entries.slice(0, 24).map(renderEntry).join("") : '<div class="cockpit-empty">No trace entries recorded.</div>',
      '</section>',
    ].join("");
    setBody(html);
  }

  async function load(runId) {
    runId = String(runId || "").trim();
    if (!runId || loadingRunId === runId) return;
    if (!window.SZ.api || typeof SZ.api.fetchDecisionTrace !== "function") return;
    loadingRunId = runId;
    setRunId(runId);
    setBody('<div class="cockpit-empty">Loading trace ' + esc(runId) + '...</div>');
    try {
      var report = await SZ.api.fetchDecisionTrace(runId);
      renderReport(report);
    } catch (err) {
      setBody('<div class="cockpit-empty">Trace unavailable: ' + esc(err.message || err) + '</div>');
    } finally {
      loadingRunId = "";
    }
  }

  function init() {
    var input = byId("blame-run-id");
    var button = byId("blame-load-btn");
    if (!input || !button) return;
    if (window.SZ.state && SZ.state.lastRunId) setRunId(SZ.state.lastRunId);
    button.addEventListener("click", function () {
      load(input.value || (window.SZ.state && SZ.state.lastRunId) || "");
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        load(input.value);
      }
    });
    if (window.SZ.subscribe) {
      SZ.subscribe("pipeline-event", function (event) {
        if (!event) return;
        if (event.run_id) setRunId(event.run_id);
        if (event.type === "STREAM_END" && (event.run_id || (SZ.state && SZ.state.lastRunId))) {
          load(event.run_id || SZ.state.lastRunId);
        }
      });
    }
  }

  window.SZ = window.SZ || {};
  window.SZ.blamePanel = { load: load, setRunId: setRunId };
  document.addEventListener("DOMContentLoaded", init);
})();
