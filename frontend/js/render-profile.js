/**
 * render-profile.js — Profile info bar
 * When chartData loads, renders: name, sector, exchange, market_cap (compact),
 * currency. Compact bar with pipe separators, dark styled.
 * Exports: SZ.renderProfile()
 */
(function () {
  "use strict";

  /* ── compact number formatter ── */
  function fmtCompact(v) {
    if (v == null || !isFinite(v)) return "—";
    if (Math.abs(v) >= 1e12)  return (v / 1e12).toFixed(1)  + "T";
    if (Math.abs(v) >= 1e9)   return (v / 1e9).toFixed(1)   + "B";
    if (Math.abs(v) >= 1e6)   return (v / 1e6).toFixed(1)    + "M";
    if (Math.abs(v) >= 1e3)   return (v / 1e3).toFixed(1)    + "K";
    return v.toFixed(2);
  }

  /* ── main render ── */
  function renderProfile() {
    var el = document.getElementById("live-profile");
    if (!el) return;

    var cd = SZ.state && SZ.state.chartData;
    var m = cd && (cd.meta || cd.profile);
    if (!m) {
      el.innerHTML = "";
      el.style.display = "none";
      return;
    }

    var parts = [];

    if (m.name)       parts.push(m.name);
    if (m.sector)     parts.push(m.sector);
    if (m.exchange)   parts.push(m.exchange);
    if (m.market_cap != null) parts.push(fmtCompact(m.market_cap));
    if (m.currency)   parts.push(m.currency);

    if (!parts.length) {
      el.innerHTML = "";
      el.style.display = "none";
      return;
    }

    el.style.display = "";
    el.innerHTML = '<span class="profile-text">' +
      parts.map(function (p) {
        return '<span class="profile-seg">' + escHtml(p) + '</span>';
      }).join('<span class="profile-pipe"> | </span>') +
      '</span>';
  }

  function escHtml(s) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
  }

  /* ── export ── */
  if (!window.SZ) window.SZ = {};
  window.SZ.renderProfile = renderProfile;
})();
