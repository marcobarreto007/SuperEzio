/* SuperEzio — Unified Trust Score
   Computes 0-100 trust score from:
   - math_coverage: MathHub modules OK (0-14)
   - data_freshness: timestamp of data vs now
   - expert_consensus: expert agreement ratio
   - f51_confidence: F51 verdict score
   Renders "TRUST: XX/100" badge in #pipeline-progress. */
(function () {
  "use strict";

  function getMathCoverage() {
    var deep = window.SZ.state && window.SZ.state.deep;
    if (!deep || !deep.math) return 0;
    var modules = deep.math.modules || {};
    var count = 0;
    for (var key in modules) {
      if (modules.hasOwnProperty(key)) {
        var mod = modules[key];
        if (mod && (mod.ok === true || mod.status === "ok" || mod.status === "done")) count++;
      }
    }
    return Math.min(14, count);
  }

  function getDataFreshness() {
    var deep = window.SZ.state && window.SZ.state.deep;
    if (!deep) return 0.5;
    var ts = deep.last_update || deep.timestamp;
    if (!ts && deep.math && deep.math.timestamp) ts = deep.math.timestamp;
    if (!ts) {
      var chartTs = window.SZ.state && window.SZ.state.chartData && window.SZ.state.chartData.fetched_at;
      if (chartTs) ts = chartTs;
    }
    if (!ts) return 0.3;
    var now = Date.now();
    var t = typeof ts === "number" ? ts : new Date(ts).getTime();
    if (isNaN(t)) return 0.3;
    var age = now - t;
    if (age < 60000)  return 1.0;
    if (age < 300000) return 0.85;
    if (age < 900000) return 0.6;
    if (age < 3600000) return 0.35;
    return 0.15;
  }

  function getExpertConsensus() {
    var deep = window.SZ.state && window.SZ.state.deep;
    if (!deep || !deep.experts) return 0;
    var experts = deep.experts;
    var count = 0;
    var bullish = 0, bearish = 0;
    for (var key in experts) {
      if (!experts.hasOwnProperty(key)) continue;
      var ex = experts[key];
      if (!ex || !ex.verdict) continue;
      count++;
      var v = String(ex.verdict).toUpperCase();
      if (v.indexOf("BULL") >= 0 || v.indexOf("BUY") >= 0 || v.indexOf("LONG") >= 0) bullish++;
      else if (v.indexOf("BEAR") >= 0 || v.indexOf("SELL") >= 0 || v.indexOf("SHORT") >= 0) bearish++;
    }
    if (count === 0) return 0;
    var max = Math.max(bullish, bearish, count - bullish - bearish);
    return max / count;
  }

  function getF51Confidence() {
    var deep = window.SZ.state && window.SZ.state.deep;
    if (!deep || !deep.f51) {
      var lastVerdict = window.SZ.state && window.SZ.state.lastF51Verdict;
      if (lastVerdict) {
        var vd = lastVerdict.data || lastVerdict;
        var sc = vd.score != null ? vd.score : vd.confidence;
        return sc != null ? Math.min(1, Math.max(0, sc)) : 0;
      }
      return 0;
    }
    var f51 = deep.f51.data || deep.f51;
    var score = f51.score != null ? f51.score : f51.confidence;
    return score != null ? Math.min(1, Math.max(0, score)) : 0;
  }

  function computeTrustScore() {
    var mc = getMathCoverage();
    var df = getDataFreshness();
    var ec = getExpertConsensus();
    var fc = getF51Confidence();

    var score = 0;
    score += (mc / 14) * 25;
    score += df * 25;
    score += ec * 25;
    score += fc * 25;
    return Math.min(100, Math.max(0, Math.round(score)));
  }

  function getScoreTone(score) {
    if (score >= 80) return "is-good";
    if (score >= 50) return "is-warn";
    return "is-bad";
  }

  function renderTrustScore() {
    var container = document.getElementById("pipeline-progress");
    if (!container) return;

    var score = computeTrustScore();
    var tone = getScoreTone(score);

    var existing = container.querySelector(".trust-score-badge");
    if (existing) {
      existing.textContent = "TRUST: " + score + "/100";
      existing.className = "trust-score-badge " + tone;
      return;
    }

    var badge = document.createElement("span");
    badge.className = "trust-score-badge " + tone;
    badge.textContent = "TRUST: " + score + "/100";
    badge.title = "Math: " + getMathCoverage() + "/14 | Freshness: " + Math.round(getDataFreshness() * 100) + "% | Consensus: " + Math.round(getExpertConsensus() * 100) + "% | F51: " + Math.round(getF51Confidence() * 100) + "%";
    container.appendChild(badge);
  }

  /* Subscribe to pipeline events for live updates */
  if (window.SZ.subscribe) {
    (function () {
      var debounceTimer = null;
      window.SZ.subscribe("pipeline-event", function () {
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(renderTrustScore, 100);
      });
    })();
  }

  /* Re-render periodically */
  window.setInterval(renderTrustScore, 5000);

  /* Initial render */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderTrustScore);
  } else {
    renderTrustScore();
  }

  /* Public API */
  window.SZ = window.SZ || {};
  window.SZ.trustScore = {
    compute: computeTrustScore,
    render: renderTrustScore,
    getMathCoverage: getMathCoverage,
    getDataFreshness: getDataFreshness,
    getExpertConsensus: getExpertConsensus,
    getF51Confidence: getF51Confidence
  };
})();
