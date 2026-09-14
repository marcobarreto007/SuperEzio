/* SuperEzio — F51 Verdict Card Renderer */
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

  var FACTORS = [
    "veracity", "consensus", "proxy_reward",
    "robustness", "uncertainty", "danger"
  ];

  var FACTOR_LABELS = {
    veracity: "Veracity",
    consensus: "Consensus",
    proxy_reward: "Proxy Reward",
    robustness: "Robustness",
    uncertainty: "Uncertainty",
    danger: "Danger"
  };

  function colorFor(v) {
    if (v == null || isNaN(v)) return "var(--muted)";
    if (v >= 0.7) return "var(--green)";
    if (v >= 0.4) return "var(--amber)";
    return "var(--red)";
  }

  function badgeClassFor(v) {
    if (v == null || isNaN(v)) return "neutral";
    if (v >= 0.7) return "pass";
    if (v >= 0.4) return "warn";
    return "fail";
  }

  function makeGauge(score) {
    var R = 32;
    var C = 2 * Math.PI * R;
    var pctVal = (score != null && !isNaN(score)) ? score : 0;
    var offset = C - (C * pctVal);

    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "f51-gauge");
    svg.setAttribute("viewBox", "0 0 80 80");
    svg.setAttribute("width", "80");
    svg.setAttribute("height", "80");

    var bgCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    bgCircle.setAttribute("cx", "40");
    bgCircle.setAttribute("cy", "40");
    bgCircle.setAttribute("r", String(R));
    bgCircle.setAttribute("fill", "none");
    bgCircle.setAttribute("stroke", "var(--line)");
    bgCircle.setAttribute("stroke-width", "6");
    svg.appendChild(bgCircle);

    var fgCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    fgCircle.setAttribute("cx", "40");
    fgCircle.setAttribute("cy", "40");
    fgCircle.setAttribute("r", String(R));
    fgCircle.setAttribute("fill", "none");
    fgCircle.setAttribute("stroke", colorFor(score));
    fgCircle.setAttribute("stroke-width", "6");
    fgCircle.setAttribute("stroke-dasharray", String(C));
    fgCircle.setAttribute("stroke-dashoffset", String(offset));
    fgCircle.setAttribute("stroke-linecap", "round");
    fgCircle.style.transform = "rotate(-90deg)";
    fgCircle.style.transformOrigin = "50% 50%";
    fgCircle.style.transition = "stroke-dashoffset 0.6s ease, stroke 0.3s ease";
    svg.appendChild(fgCircle);

    var txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", "40");
    txt.setAttribute("y", "44");
    txt.setAttribute("text-anchor", "middle");
    txt.setAttribute("fill", "var(--ink)");
    txt.setAttribute("font-size", "14");
    txt.setAttribute("font-weight", "700");
    txt.textContent = pct(score);
    svg.appendChild(txt);

    return svg;
  }

  function makeFactorBar(name, value) {
    var row = SZ.dom.el("div", "f51-factor");
    var label = SZ.dom.el("span", "f51-factor__label");
    label.textContent = FACTOR_LABELS[name] || name;
    var track = SZ.dom.el("div", "f51-factor__track");
    var fill = SZ.dom.el("div", "f51-factor__fill");
    var pctVal = (value != null && !isNaN(value)) ? value : 0;
    fill.style.width = (pctVal * 100) + "%";
    fill.style.background = colorFor(value);
    fill.style.transition = "width 0.4s ease, background 0.3s ease";
    track.appendChild(fill);
    var val = SZ.dom.el("span", "f51-factor__value");
    val.textContent = pct(value);
    row.append(label, track, val);
    return row;
  }

  function renderF51(ev, ceo) {
    var data = ev && ev.data ? ev.data : ev;
    if (!data) return;

    var verdict = data.verdict || data.f51_verdict || data;
    var score = verdict.score != null ? verdict.score : null;
    if (score == null && verdict.composite != null) score = verdict.composite;

    var hubRisk = verdict.hub_risk != null ? verdict.hub_risk : null;
    var badgeText = score != null ? pct(score) : "--";
    var badgeCls = badgeClassFor(score);

    var info = SZ.cards.makeCard("F51 Verdict", badgeText, badgeCls, "shield-check");
    info.card.classList.add("card--f51");


    var inner = SZ.dom.el("div", "f51-inner");

    // Gauge
    var gaugeWrap = SZ.dom.el("div", "f51-gauge-wrap");
    gaugeWrap.appendChild(makeGauge(score));
    inner.appendChild(gaugeWrap);

    // Factor bars
    var factorsWrap = SZ.dom.el("div", "f51-factors");
    FACTORS.forEach(function (name) {
      var val = verdict[name] != null ? verdict[name] : null;
      if (val == null && verdict.factors && verdict.factors[name] != null) {
        val = verdict.factors[name];
      }
      factorsWrap.appendChild(makeFactorBar(name, val));
    });
    inner.appendChild(factorsWrap);

    // Hub risk bar
    if (hubRisk != null) {
      var hubRow = SZ.dom.el("div", "f51-hub-risk");
      var hubLabel = SZ.dom.el("span", "f51-factor__label");
      hubLabel.textContent = "Hub Risk";
      var hubTrack = SZ.dom.el("div", "f51-factor__track");
      var hubFill = SZ.dom.el("div", "f51-factor__fill");
      hubFill.style.width = (hubRisk * 100) + "%";
      hubFill.style.background = colorFor(hubRisk);
      hubFill.style.transition = "width 0.4s ease, background 0.3s ease";
      hubTrack.appendChild(hubFill);
      var hubVal = SZ.dom.el("span", "f51-factor__value");
      hubVal.textContent = pct(hubRisk);
      hubRow.append(hubLabel, hubTrack, hubVal);
      inner.appendChild(hubRow);
    }

    info.body.appendChild(inner);

    // Stamp AFTER the card is in the DOM, so it paints on first try.
    // F51_VERDICT carries no timestamp (src/core/pipeline/nodes/f51.py:48
    // sends confidence / decision_score / factors only) -> receipt clock.
    stampCard(info.card, ev, "F51_VERDICT");

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

  window.SZ.renderF51 = renderF51;
})();
