/* SuperEzio — Data Quality Card Renderer */
(function () {
  "use strict";

  function pct(v) {
    return (v != null && !isNaN(v)) ? Math.round(v * 100) + "%" : "--";
  }

  function fmt(v, d) {
    if (d === undefined) d = 2;
    return (v != null && !isNaN(v)) ? Number(v).toFixed(d) : "--";
  }

  function lastVal(series) {
    if (!Array.isArray(series) || series.length === 0) return null;
    var last = series[series.length - 1];
    return (last && last.value != null) ? last.value : null;
  }

  var SOURCES = [
    "technicals", "profile", "quant", "risk", "sentiment",
    "reddit", "macro", "crisis", "realtime_price", "quantum"
  ];

  var SOURCE_LABELS = {
    technicals: "Technicals",
    profile: "Profile",
    quant: "Quant",
    risk: "Risk",
    sentiment: "Sentiment",
    reddit: "Reddit",
    macro: "Macro",
    crisis: "Crisis",
    realtime_price: "Realtime Price",
    quantum: "Quantum"
  };

  function statusColor(status) {
    if (!status) return "var(--muted)";
    var s = String(status).toLowerCase().trim();
    if (s === "ok" || s === "provider" || s === "computed") return "var(--green)";
    if (s === "partial") return "var(--amber)";
    return "var(--red)";
  }

  function statusIcon(status) {
    if (!status) return "○";
    var s = String(status).toLowerCase().trim();
    if (s === "ok" || s === "provider" || s === "computed") return "●";
    if (s === "partial") return "◐";
    return "✗";
  }

  function normalizeStatus(status) {
    if (status == null) return "";
    if (typeof status === "boolean") return status ? "ok" : "error";
    if (typeof status === "object") {
      return String(status.status || status.state || status.result || (status.error ? "error" : "ok"));
    }
    return String(status);
  }

  function makeTile(source, status) {
    var normalized = normalizeStatus(status);
    var tile = SZ.dom.el("div", "dq-tile");
    tile.classList.add("dq-tile--" + (normalized || "unknown").toLowerCase().replace(/[^a-z]/g, "-"));

    var icon = SZ.dom.el("span", "dq-tile__icon");
    icon.textContent = statusIcon(normalized);
    icon.style.color = statusColor(normalized);
    tile.appendChild(icon);

    var label = SZ.dom.el("span", "dq-tile__label");
    label.textContent = SOURCE_LABELS[source] || source;
    tile.appendChild(label);

    var statusEl = SZ.dom.el("span", "dq-tile__status");
    statusEl.textContent = normalized ? normalized.toUpperCase() : "--";
    statusEl.style.color = statusColor(normalized);
    tile.appendChild(statusEl);

    return tile;
  }

  function countOk(sources) {
    var ok = 0, total = 0;
    SOURCES.forEach(function (key) {
      var s = sources[key];
      if (s != null) {
        total++;
        var sv = normalizeStatus(s).toLowerCase().trim();
        if (sv === "ok" || sv === "provider" || sv === "computed") ok++;
      }
    });
    return { ok: ok, total: total || SOURCES.length };
  }

  function renderDataQuality(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var dq = data.data_quality || data.sources || data;
    var sources = dq.sources || dq;

    var counts = countOk(sources);
    var badgeText = counts.ok + "/" + counts.total;
    var pctOk = counts.total > 0 ? counts.ok / counts.total : 0;
    var badgeCls = pctOk >= 0.8 ? "pass" : (pctOk >= 0.5 ? "warn" : "fail");

    var info = SZ.cards.makeCard("Data Quality", badgeText, badgeCls, "database");
    info.card.classList.add("card--data-quality");

    var grid = SZ.dom.el("div", "dq-grid");

    SOURCES.forEach(function (key) {
      var status = sources[key] != null ? sources[key] : null;
      grid.appendChild(makeTile(key, status));
    });

    info.body.appendChild(grid);

    // Insert into CEO bubble
    var bubble = ceo.bubble;
    var anchor = bubble.querySelector(".pipeline-bar");
    if (anchor && anchor.nextSibling) {
      bubble.insertBefore(info.card, anchor.nextSibling);
    } else if (anchor) {
      bubble.appendChild(info.card);
    } else {
      bubble.appendChild(info.card);
    }

    return info;
  }

  window.SZ.renderDataQuality = renderDataQuality;
})();
