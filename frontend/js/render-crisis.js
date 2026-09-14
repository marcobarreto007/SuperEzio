/* SuperEzio — Crisis Radar Card Renderer */
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

  function lastVal(series) {
    if (!Array.isArray(series) || series.length === 0) return null;
    var last = series[series.length - 1];
    return (last && last.value != null) ? last.value : null;
  }

  var MODEL_KEYS = [
    "bis_credit_gap", "markov_regime", "hawkes_stress", "lppls_bubble",
    "yield_curve", "leverage_cycle", "vol_clustering", "contagion",
    "flight_quality", "illiquidity", "sentiment_crisis", "macro_stress"
  ];

  var MODEL_LABELS = {
    bis_credit_gap: "BIS Credit Gap",
    markov_regime: "Markov Regime",
    hawkes_stress: "Hawkes Stress",
    lppls_bubble: "LPPLS Bubble",
    yield_curve: "Yield Curve",
    leverage_cycle: "Leverage Cycle",
    vol_clustering: "Vol Clustering",
    contagion: "Contagion",
    flight_quality: "Flight Quality",
    illiquidity: "Illiquidity",
    sentiment_crisis: "Sentiment Crisis",
    macro_stress: "Macro Stress"
  };

  function regimeBadgeClass(regime) {
    if (!regime) return "neutral";
    var r = String(regime).toLowerCase().trim();
    if (r === "normal") return "pass";
    if (r === "stress") return "warn";
    return "fail";
  }

  function colorForModel(v) {
    if (v == null || isNaN(v)) return "var(--muted)";
    if (v <= 0.3) return "var(--green)";
    if (v <= 0.6) return "var(--amber)";
    return "var(--red)";
  }

  function modelValue(raw) {
    if (raw == null) return null;
    if (typeof raw === "object" && raw.score != null) return raw.score;
    return typeof raw === "number" ? raw : null;
  }

  function makeModelTile(key, raw) {
    var val = modelValue(raw);
    var tile = SZ.dom.el("div", "crisis-model-tile");
    var label = SZ.dom.el("span", "crisis-model-tile__label");
    label.textContent = MODEL_LABELS[key] || key;
    var bar = SZ.dom.el("div", "crisis-model-tile__bar");
    var fill = SZ.dom.el("div", "crisis-model-tile__fill");
    var pctVal = (val != null && !isNaN(val)) ? val : 0;
    fill.style.width = (pctVal * 100) + "%";
    fill.style.background = colorForModel(val);
    fill.style.transition = "width 0.4s ease, background 0.3s ease";
    bar.appendChild(fill);
    var valEl = SZ.dom.el("span", "crisis-model-tile__value");
    valEl.textContent = (val != null && !isNaN(val)) ? pct(val) : "--";
    tile.append(label, bar, valEl);
    return tile;
  }

  function renderAlerts(alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) return null;
    var wrap = SZ.dom.el("div", "crisis-alerts");
    var lbl = SZ.dom.el("div", "cris-alerts__title");
    lbl.textContent = "Alerts";
    wrap.appendChild(lbl);
    var pills = SZ.dom.el("div", "crisis-alerts__pills");
    alerts.forEach(function (a) {
      var pill = SZ.dom.el("span", "crisis-alert-pill");
      var severity = (typeof a === "object" && a.severity) ? a.severity : "warn";
      pill.classList.add("crisis-alert-pill--" + String(severity).toLowerCase());
      pill.textContent = typeof a === "string" ? SZ.esc(a) : SZ.esc(a.message || a.text || String(a));
      pills.appendChild(pill);
    });
    wrap.appendChild(pills);
    return wrap;
  }

  function makeRiskBar(label, value) {
    var row = SZ.dom.el("div", "crisis-risk-bar");
    var lbl = SZ.dom.el("span", "crisis-risk-bar__label");
    lbl.textContent = label;
    var track = SZ.dom.el("div", "crisis-risk-bar__track");
    var fill = SZ.dom.el("div", "crisis-risk-bar__fill");
    var pctVal = (value != null && !isNaN(value)) ? value : 0;
    fill.style.width = (pctVal * 100) + "%";
    fill.style.background = colorForModel(value);
    fill.style.transition = "width 0.4s ease, background 0.3s ease";
    track.appendChild(fill);
    var valEl = SZ.dom.el("span", "crisis-risk-bar__value");
    valEl.textContent = pct(value);
    row.append(lbl, track, valEl);
    return row;
  }

  function renderCrisis(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var crisis = data.crisis || data.crisis_radar || data;
    var regime = crisis.regime || crisis.regime_label || null;
    var systemicRisk = crisis.systemic_risk != null ? crisis.systemic_risk : null;
    var alerts = crisis.alerts || [];

    var badgeText = regime ? String(regime).toUpperCase() : "--";
    var badgeCls = regimeBadgeClass(regime);

    var info = SZ.cards.makeCard("Crisis Radar", badgeText, badgeCls, "radar");
    info.card.classList.add("card--crisis");


    // Regime badge area
    if (regime) {
      var regimeEl = SZ.dom.el("div", "crisis-regime crisis-regime--" + String(regime).toLowerCase());
      regimeEl.textContent = "Regime: " + String(regime).toUpperCase();
      info.body.appendChild(regimeEl);
    }

    // Systemic risk bar
    if (systemicRisk != null) {
      info.body.appendChild(makeRiskBar("Systemic Risk", systemicRisk));
    }

    // Alerts
    var alertsEl = renderAlerts(alerts);
    if (alertsEl) info.body.appendChild(alertsEl);

    // Model grid (3x4)
    var grid = SZ.dom.el("div", "crisis-model-grid");
    var models = crisis.models || crisis;
    MODEL_KEYS.forEach(function (key) {
      var raw = models[key] != null ? models[key] : null;
      grid.appendChild(makeModelTile(key, raw));
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

    // Stamp AFTER insertion. CRISIS_MATH carries no timestamp
    // (src/core/pipeline/nodes/f51.py:83 sends systemic_risk / regime /
    // alert only) -> receipt clock.
    stampCard(info.card, ev, "CRISIS_MATH");

    return info;
  }

  window.SZ.renderCrisis = renderCrisis;
})();
