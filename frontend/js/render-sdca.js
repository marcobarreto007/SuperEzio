/* SuperEzio — SDCA Firewall Card Renderer */
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

  var METRICS = [
    { key: "confidence",     label: "Confidence" },
    { key: "uncertainty",    label: "Uncertainty" },
    { key: "utility",        label: "Utility" },
    { key: "experiences",    label: "Experiences", isCount: true },
    { key: "truthfulness",   label: "Truthfulness" },
    { key: "chaos_reduction", label: "Chaos Reduction" }
  ];

  function decisionBadgeClass(decision) {
    if (!decision) return "neutral";
    var d = String(decision).toUpperCase().trim();
    if (d === "ALLOW") return "pass";
    if (d === "BLOCK") return "fail";
    if (d === "REVIEW") return "warn";
    return "neutral";
  }

  function makeMetricRow(label, value, isCount) {
    var row = SZ.dom.el("div", "sdca-metric");
    var lbl = SZ.dom.el("span", "sdca-metric__label");
    lbl.textContent = label;
    var val = SZ.dom.el("span", "sdca-metric__value");
    if (isCount) {
      val.textContent = (value != null && !isNaN(value)) ? Math.round(value) : "--";
    } else {
      val.textContent = (value != null && !isNaN(value)) ? pct(value) : "--";
    }
    row.append(lbl, val);
    return row;
  }

  function renderGhostTokens(tokens) {
    if (!Array.isArray(tokens) || tokens.length === 0) return null;
    var wrap = SZ.dom.el("div", "sdca-ghost-tokens");
    var lbl = SZ.dom.el("span", "sdca-ghost-tokens__label");
    lbl.textContent = "Ghost Tokens";
    wrap.appendChild(lbl);
    var row = SZ.dom.el("div", "sdca-ghost-tokens__row");
    var max = Math.min(tokens.length, 8);
    for (var i = 0; i < max; i++) {
      var chip = SZ.dom.el("span", "sdca-ghost-chip");
      chip.textContent = SZ.esc(String(tokens[i]));
      chip.setAttribute("title", String(tokens[i]));
      row.appendChild(chip);
    }
    if (tokens.length > 8) {
      var more = SZ.dom.el("span", "sdca-ghost-chip sdca-ghost-chip--more");
      more.textContent = "+" + (tokens.length - 8);
      row.appendChild(more);
    }
    wrap.appendChild(row);
    return wrap;
  }

  function renderSDCA(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var sdca = data.sdca || data.sdca_firewall || data;
    var decision = sdca.decision || sdca.action || null;
    var summary = sdca.human_summary || sdca.summary || null;
    var badgeText = decision ? String(decision).toUpperCase() : "--";
    var badgeCls = decisionBadgeClass(decision);

    var info = SZ.cards.makeCard("SDCA Firewall", badgeText, badgeCls, "flame");
    info.card.classList.add("card--sdca");

    // Decision banner
    if (decision) {
      var banner = SZ.dom.el("div", "sdca-decision sdca-decision--" + String(decision).toLowerCase());
      banner.textContent = String(decision).toUpperCase();
      info.body.appendChild(banner);
    }

    // Human summary
    if (summary) {
      var summaryEl = SZ.dom.el("div", "sdca-summary");
      summaryEl.textContent = summary;
      info.body.appendChild(summaryEl);
    }

    // Metrics grid
    var grid = SZ.dom.el("div", "sdca-metrics-grid");
    METRICS.forEach(function (m) {
      var val = sdca[m.key] != null ? sdca[m.key] : null;
      if (val == null && sdca.metrics && sdca.metrics[m.key] != null) {
        val = sdca.metrics[m.key];
      }
      grid.appendChild(makeMetricRow(m.label, val, m.isCount));
    });
    info.body.appendChild(grid);

    // Ghost tokens
    var tokens = sdca.ghost_tokens || sdca.tokens || null;
    var tokenEl = renderGhostTokens(tokens);
    if (tokenEl) info.body.appendChild(tokenEl);

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

  window.SZ.renderSDCA = renderSDCA;
})();
