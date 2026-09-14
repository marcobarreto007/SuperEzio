/* SuperEzio — Neural Decision Card Renderer */
(function () {
  "use strict";

  /* Freshness stamp — implemented in render-pipeline.js (loaded first).
   * Resolved at call time so script order is irrelevant. */
  function stampCard(card, ev, label) {
    if (SZ.stamp && SZ.stamp.card) SZ.stamp.card(card, ev, label);
  }

  function pct(v) {
    return (v != null && !isNaN(v)) ? Math.round(v * 100) + "%" : "--";
  }

  function fmt(v, d) {
    if (d === undefined) d = 2;
    return (v != null && !isNaN(v)) ? Number(v).toFixed(d) : "--";
  }

  function fmtCompact(v) {
    if (v == null || isNaN(v)) return "--";
    var abs = Math.abs(v);
    var sign = v < 0 ? "-" : "";
    if (abs >= 1e12) return sign + (abs / 1e12).toFixed(1) + "T";
    if (abs >= 1e9)  return sign + (abs / 1e9).toFixed(1) + "B";
    if (abs >= 1e6)  return sign + (abs / 1e6).toFixed(1) + "M";
    if (abs >= 1e3)  return sign + (abs / 1e3).toFixed(1) + "K";
    return sign + abs.toFixed(1);
  }

  function lastVal(series) {
    if (!Array.isArray(series) || series.length === 0) return null;
    var last = series[series.length - 1];
    return (last && last.value != null) ? last.value : null;
  }

  var DIRECTIONS = [
    { key: "up",       label: "UP",       color: "var(--green)" },
    { key: "down",     label: "DOWN",     color: "var(--red)" },
    { key: "sideways", label: "SIDEWAYS", color: "var(--amber)" }
  ];

  var RECOMMENDATION_CLASSES = {
    veto_block: "fail",
    alerta_forte: "warn",
    alerta_fraco: "neutral",
    observar: "pass"
  };

  function colorForProb(v) {
    if (v == null || isNaN(v)) return "var(--muted)";
    if (v >= 0.6) return "var(--green)";
    if (v >= 0.3) return "var(--amber)";
    return "var(--red)";
  }

  function makeDirectionBar(dir, value) {
    var row = SZ.dom.el("div", "neural-dir");
    var label = SZ.dom.el("span", "neural-dir__label");
    label.textContent = dir.label;
    label.style.color = dir.color;
    label.style.minWidth = "80px";

    var track = SZ.dom.el("div", "neural-dir__track");
    var fill = SZ.dom.el("div", "neural-dir__fill");
    var pctVal = (value != null && !isNaN(value)) ? value : 0;
    fill.style.width = (pctVal * 100) + "%";
    fill.style.background = dir.color;
    fill.style.transition = "width 0.4s ease";
    track.appendChild(fill);

    var val = SZ.dom.el("span", "neural-dir__value");
    val.textContent = (value != null && !isNaN(value)) ? pct(value) : "--";
    val.style.minWidth = "40px";
    val.style.textAlign = "right";

    row.append(label, track, val);
    return row;
  }

  function makePercentBar(label, value, invertColor) {
    var row = SZ.dom.el("div", "neural-bar");
    var lbl = SZ.dom.el("span", "neural-bar__label");
    lbl.textContent = label;

    var track = SZ.dom.el("div", "neural-bar__track");
    var fill = SZ.dom.el("div", "neural-bar__fill");
    var absVal = (value != null && !isNaN(value)) ? Math.abs(value) : 0;
    fill.style.width = Math.min(absVal * 100, 100) + "%";

    var color;
    if (invertColor) {
      color = absVal <= 0.3 ? "var(--green)" : (absVal <= 0.6 ? "var(--amber)" : "var(--red)");
    } else {
      color = absVal >= 0.6 ? "var(--green)" : (absVal >= 0.3 ? "var(--amber)" : "var(--red)");
    }
    fill.style.background = color;
    fill.style.transition = "width 0.4s ease, background 0.3s ease";
    track.appendChild(fill);

    var valEl = SZ.dom.el("span", "neural-bar__value");
    valEl.textContent = (value != null && !isNaN(value)) ? pct(value) : "--";

    row.append(lbl, track, valEl);
    return row;
  }

  function renderNeural(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var neural = data.neural || data.neural_decision || data;

    var directionProb = neural.direction_prob || {};
    var expectedReturn = neural.expected_return != null ? neural.expected_return : null;
    var drawdownRisk = neural.drawdown_risk != null ? neural.drawdown_risk : null;
    var uncertainty = neural.uncertainty != null ? neural.uncertainty : null;
    var regime = neural.regime || null;
    var recommendation = neural.recommendation || null;
    var veto = neural.veto || false;
    var reason = neural.reason || null;

    // Badge text
    var badgeText = "--";
    if (recommendation) badgeText = String(recommendation).toUpperCase();
    else if (regime) badgeText = String(regime).toUpperCase();

    var badgeCls = RECOMMENDATION_CLASSES[recommendation] || "neutral";
    if (veto) badgeCls = "fail";

    var info = SZ.cards.makeCard("Neural Decision", badgeText, badgeCls, "brain");
    info.card.classList.add("card--neural");


    // Veto warning banner
    if (veto) {
      var vetoBanner = SZ.dom.el("div", "neural-veto-banner");
      vetoBanner.textContent = "VETO ACTIVE";
      vetoBanner.style.background = "var(--red)";
      vetoBanner.style.color = "#fff";
      vetoBanner.style.padding = "6px 12px";
      vetoBanner.style.borderRadius = "4px";
      vetoBanner.style.fontWeight = "700";
      vetoBanner.style.textAlign = "center";
      vetoBanner.style.marginBottom = "8px";
      info.body.appendChild(vetoBanner);
      info.card.style.boxShadow = "0 0 0 2px var(--red)";
    }

    // Direction probabilities
    var dirWrap = SZ.dom.el("div", "neural-dirs");
    DIRECTIONS.forEach(function (dir) {
      var val = directionProb[dir.key] != null ? directionProb[dir.key] : null;
      dirWrap.appendChild(makeDirectionBar(dir, val));
    });
    info.body.appendChild(dirWrap);

    // Regime badge
    if (regime) {
      var regimeEl = SZ.dom.el("div", "neural-regime");
      regimeEl.innerHTML = "<span class=\"neural-regime__label\">Regime:</span> <span class=\"neural-regime__value\">" + SZ.esc(String(regime)) + "</span>";
      info.body.appendChild(regimeEl);
    }

    // Recommendation badge
    if (recommendation) {
      var recEl = SZ.dom.el("div", "neural-rec neural-rec--" + (RECOMMENDATION_CLASSES[recommendation] || "neutral"));
      recEl.textContent = String(recommendation).toUpperCase().replace(/_/g, " ");
      info.body.appendChild(recEl);
    }

    // Expected return bar
    if (expectedReturn != null) {
      info.body.appendChild(makePercentBar("Expected Return", expectedReturn, false));
    }

    // Drawdown risk bar
    if (drawdownRisk != null) {
      info.body.appendChild(makePercentBar("Drawdown Risk", drawdownRisk, true));
    }

    // Uncertainty bar
    if (uncertainty != null) {
      info.body.appendChild(makePercentBar("Uncertainty", uncertainty, true));
    }

    // Reason text
    if (reason) {
      var reasonEl = SZ.dom.el("div", "neural-reason");
      reasonEl.textContent = reason;
      reasonEl.style.color = "var(--muted)";
      reasonEl.style.fontSize = "0.85em";
      reasonEl.style.marginTop = "8px";
      reasonEl.style.fontStyle = "italic";
      info.body.appendChild(reasonEl);
    }

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

    // Stamp AFTER insertion. This is the only card whose payload carries
    // a real producer timestamp: the backend writes NEURAL_DECISION with
    // `as_of` (src/core/pipeline/nodes/neural_decision.py:103). It is a
    // BAR time, not a wall clock — so it will honestly read as old when
    // the forecast rests on old candles.
    stampCard(info.card, ev, "NEURAL_DECISION");

    return info;
  }

  window.SZ.renderNeural = renderNeural;
})();
