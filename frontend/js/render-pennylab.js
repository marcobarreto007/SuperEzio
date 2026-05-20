/* SuperEzio — PennyLab Card Renderer */
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

  var SCORES = [
    { key: "whale_suspicion",  label: "Whale Suspicion" },
    { key: "pump_probability",  label: "Pump Probability" },
    { key: "trap_risk",         label: "Trap Risk" },
    { key: "liquidity_risk",    label: "Liquidity Risk" },
    { key: "expected_loss",     label: "Expected Loss" }
  ];

  function colorForScore(v) {
    if (v == null || isNaN(v)) return "var(--muted)";
    if (v <= 0.3) return "var(--green)";
    if (v <= 0.6) return "var(--amber)";
    return "var(--red)";
  }

  function decisionBadgeClass(decision) {
    if (!decision) return "neutral";
    var d = String(decision).toLowerCase().trim();
    if (d === "bullish") return "pass";
    if (d === "bearish") return "fail";
    if (d === "no_trade" || d === "no-trade") return "neutral";
    return "neutral";
  }

  function makeScoreBar(label, value) {
    var row = SZ.dom.el("div", "penny-score");
    var lbl = SZ.dom.el("span", "penny-score__label");
    lbl.textContent = label;
    var track = SZ.dom.el("div", "penny-score__track");
    var fill = SZ.dom.el("div", "penny-score__fill");
    var pctVal = (value != null && !isNaN(value)) ? value : 0;
    fill.style.width = (pctVal * 100) + "%";
    fill.style.background = colorForScore(value);
    fill.style.transition = "width 0.4s ease, background 0.3s ease";
    track.appendChild(fill);
    var val = SZ.dom.el("span", "penny-score__value");
    val.textContent = (value != null && !isNaN(value)) ? fmt(value) : "--";
    row.append(lbl, track, val);
    return row;
  }

  function renderPennylab(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var penny = data.pennylab || data.penny_lab || data;
    var decision = penny.decision || penny.signal || null;
    var badgeText = decision ? String(decision).toUpperCase() : "--";
    var badgeCls = decisionBadgeClass(decision);

    var info = SZ.cards.makeCard("PennyLab", badgeText, badgeCls, "flask-conical");
    info.card.classList.add("card--pennylab");

    // Decision badge area
    if (decision) {
      var decEl = SZ.dom.el("div", "penny-decision penny-decision--" + String(decision).toLowerCase().replace(/_/g, "-"));
      decEl.textContent = String(decision).toUpperCase().replace(/_/g, " ");
      info.body.appendChild(decEl);
    }

    // Score bars
    var scoresWrap = SZ.dom.el("div", "penny-scores");
    SCORES.forEach(function (s) {
      var val = penny[s.key] != null ? penny[s.key] : null;
      if (val == null && penny.scores && penny.scores[s.key] != null) {
        val = penny.scores[s.key];
      }
      scoresWrap.appendChild(makeScoreBar(s.label, val));
    });
    info.body.appendChild(scoresWrap);

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

  window.SZ.renderPennylab = renderPennylab;
})();
