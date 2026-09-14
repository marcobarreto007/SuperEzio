/* SuperEzio -- Alert & Notification System */
(function () {
  "use strict";
  var MAX_ALERTS = 50;
  var TOAST_DURATION = 5000;
  var SERVER_ALERTS_ENDPOINT = "/sentiment/alerts";
  var alerts = [];
  var unreadCount = 0;
  /* Origin bookkeeping: alerts born in this browser ("local") are not server
     state, and the badge must not imply they are. Server alerts come from
     /sentiment/alerts (GET, read-only, already served by the backend). */
  var serverState = "loading"; /* loading | ok | error */
  var serverCount = 0;

  /* -- Persistence (local items only; server items are re-hydrated) -- */
  function load() {
    try { var s = localStorage.getItem("sz_alerts"); if (s) { var p = JSON.parse(s); if (Array.isArray(p)) { alerts = p.slice(0, MAX_ALERTS).map(function (aa) { aa.source = "local"; return aa; }); unreadCount = alerts.filter(function(aa){return !aa.read}).length; } } } catch(e){ console.warn("[alerts] cache local ilegivel (sz_alerts), comecando vazio:", e); }
  }

  function save() {
    try {
      var local = alerts.filter(function (aa) { return aa.source !== "server"; });
      localStorage.setItem("sz_alerts", JSON.stringify(local.slice(0, MAX_ALERTS)));
    } catch(e){ console.warn("[alerts] nao foi possivel gravar o cache local de alertas:", e); }
  }

  function loadServerReadIds() {
    try { var s = localStorage.getItem("sz_alerts_server_read"); var p = s ? JSON.parse(s) : []; return Array.isArray(p) ? p : []; } catch (e) { return []; }
  }
  function saveServerReadIds(ids) {
    try { localStorage.setItem("sz_alerts_server_read", JSON.stringify(ids.slice(-200))); } catch (e) { /* storage off: read state stays session-only */ }
  }
  var serverReadIds = loadServerReadIds();


  /* -- Alert CRUD -- */
  function add(type, title, description, data) {
    var alert = {
      id: Date.now() + "-" + Math.random().toString(16).slice(2, 8),
      type: type,
      title: String(title),
      description: String(description || ""),
      data: data || {},
      ts: new Date().toISOString(),
      read: false,
      source: "local"
    };
    alerts.unshift(alert);
    if (alerts.length > MAX_ALERTS) alerts.length = MAX_ALERTS;
    unreadCount++;
    save();
    renderBadge();
    return alert;
  }

  /* ── Server alerts (/sentiment/alerts) ──
     Each item is turned into the same shape the list already renders, plus
     source:"server". Nothing is invented: an item whose fields are unknown
     still says "sem dado" instead of a fabricated score. */
  function describeServerAlert(a) {
    var ticker = a.ticker || a.symbol || "?";
    if (a.delta != null) return { title: "Sentimento virou em " + ticker, description: "score " + a.from + " -> " + a.to + " (delta " + a.delta + ")" };
    if (a.count != null) return { title: "Pico de mencoes em " + ticker, description: a.count + " mencoes vs media " + a.avg };
    if (a.accounts != null) return { title: "Contas coordenadas em " + ticker, description: a.accounts + " contas no mesmo movimento" };
    if (a.institutional || a.social) return { title: "Divergencia institucional x social em " + ticker, description: "social: " + (a.social || "sem dado") };
    return { title: String(a.type || "ALERTA") + " " + ticker, description: "sem detalhe enviado pelo servidor" };
  }

  function mapServerAlert(a) {
    var type = String((a && a.type) || "SENTIMENT").toUpperCase();
    var ts = (a && (a.detected_at || a.ts || a.timestamp)) || null;
    var text = describeServerAlert(a || {});
    var id = "srv-" + type + "-" + ((a && (a.ticker || a.symbol)) || "?") + "-" + (ts || "");
    return {
      id: id,
      type: "SENTIMENT",
      rawType: type,
      title: text.title,
      description: text.description,
      data: a || {},
      ts: ts || new Date().toISOString(),
      read: serverReadIds.indexOf(id) >= 0,
      source: "server"
    };
  }

  async function hydrateFromServer() {
    var api = window.SZ && window.SZ.api;
    if (!api || typeof api.fetchSentimentAlerts !== "function") {
      serverState = "error";
      renderBadge();
      renderList();
      return null;
    }
    try {
      var payload = await api.fetchSentimentAlerts(20);
      var list = (payload && Array.isArray(payload.alerts)) ? payload.alerts : [];
      var serverAlerts = list.map(mapServerAlert);
      serverCount = serverAlerts.length;
      alerts = alerts.filter(function (aa) { return aa.source !== "server"; }).concat(serverAlerts);
      alerts.sort(function (x, y) { return new Date(y.ts) - new Date(x.ts); });
      if (alerts.length > MAX_ALERTS) alerts.length = MAX_ALERTS;
      unreadCount = alerts.filter(function (aa) { return !aa.read; }).length;
      serverState = "ok";
      renderBadge();
      renderList();
      return serverAlerts;
    } catch (e) {
      serverState = "error";
      console.warn("[alerts] falha ao consultar " + SERVER_ALERTS_ENDPOINT + ":", e);
      renderBadge();
      renderList();
      return null;
    }
  }

  function markRead(id) {
    for (var i = 0; i < alerts.length; i++) {
      if (alerts[i].id === id && !alerts[i].read) {
        alerts[i].read = true;
        if (alerts[i].source === "server" && serverReadIds.indexOf(id) < 0) {
          serverReadIds.push(id);
          saveServerReadIds(serverReadIds);
        }
        unreadCount = Math.max(0, unreadCount - 1);
        save(); renderBadge(); renderList();
        return;
      }
    }
  }

  function markAllRead() {
    for (var i = 0; i < alerts.length; i++) {
      alerts[i].read = true;
      if (alerts[i].source === "server" && serverReadIds.indexOf(alerts[i].id) < 0) serverReadIds.push(alerts[i].id);
    }
    saveServerReadIds(serverReadIds);
    unreadCount = 0; save(); renderBadge(); renderList();
  }

  function getUnreadCount() { return unreadCount; }
  function getAlerts() { return alerts.slice(); }
  function getServerState() { return { state: serverState, count: serverCount, endpoint: SERVER_ALERTS_ENDPOINT }; }

  /* -- Icons & colors -- */
  function getIcon(type) {
    switch (type) {
      case "MANGALA": return "🎯";
      case "WHALE": return "🐋";
      case "GUARDRAIL": return "🛡️";
      case "TRADE": return "💰";
      case "SYSTEM": return "⚙️";
      case "SENTIMENT": return "📡";
      default: return "🔔";
    }
  }

  function getTypeColor(type) {
    switch (type) {
      case "MANGALA": return "#ff9800";
      case "WHALE": return "#00e5ff";
      case "GUARDRAIL": return "#ef5350";
      case "TRADE": return "#00e676";
      case "SYSTEM": return "#90a4ae";
      case "SENTIMENT": return "#b388ff";
      default: return "#58a6ff";
    }
  }

  function formatTime(ts) {
    var d = new Date(ts); var now = new Date(); var diff = now - d;
    if (diff < 60000) return "agora";
    if (diff < 3600000) return Math.floor(diff/60000) + "m";
    if (diff < 86400000) return Math.floor(diff/3600000) + "h";
    return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  }

  function esc(s) {
    var d = document.createElement("div");
    d.appendChild(document.createTextNode(String(s)));
    return d.innerHTML;
  }

  /* ===== UI: BADGE ===== */
  function renderBadge() {
    var badge = document.getElementById("alert-badge-count");
    var btn = document.getElementById("alert-bell-btn");
    if (!badge || !btn) return;
    if (unreadCount > 0) {
      badge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
      badge.style.display = "flex";
      btn.classList.add("has-alerts");
    } else {
      badge.style.display = "none";
      btn.classList.remove("has-alerts");
    }
  }

  /* ===== UI: DROPDOWN LIST ===== */
  function renderList() {
    var container = document.getElementById("alert-list");
    if (!container) return;
    var localCount = alerts.filter(function (aa) { return aa.source !== "server"; }).length;
    var origin = serverState === "ok"
      ? "servidor " + serverCount + " · local " + localCount
      : (serverState === "loading" ? "servidor: consultando..." : "servidor: SEM DADO (" + SERVER_ALERTS_ENDPOINT + ")");
    /* Styled inline: this file may not touch frontend/css/*.css. */
    var originHtml = '<div class="alert-list__origin" style="padding:4px 12px 6px;font-size:11px;opacity:.7">' + esc(origin) + '</div>';
    if (alerts.length === 0) {
      container.innerHTML = '<div class="alert-list__empty">Nenhum alerta.</div>' + originHtml;
      return;
    }
    var h = '<div class="alert-list__header"><span class="alert-list__count">' + unreadCount + ' nao lidos</span>';
    h += '<button class="alert-list__mark-read" id="alert-mark-all-read" type="button">Marcar tudo lido</button></div>';
    /* The badge belongs to the local UI as much as to the backend; say which
       is which instead of letting both look like server state. */
    h += originHtml;
    h += '<div class="alert-list__items">';
    for (var i = 0; i < alerts.length; i++) {
      var a = alerts[i];
      var icon = getIcon(a.type);
      var color = getTypeColor(a.type);
      h += '<div class="alert-item' + (a.read ? ' alert-item--read' : '') + '" data-alert-id="' + esc(a.id) + '">';
      h += '<span class="alert-item__icon" style="color:' + color + '">' + icon + '</span>';
      h += '<div class="alert-item__body"><div class="alert-item__title">' + esc(a.title) + '</div>';
      h += '<div class="alert-item__desc">' + esc(a.description) + '</div>';
      h += '<div class="alert-item__ts">' + (a.source === "server" ? "servidor · " : "local · ") + formatTime(a.ts) + '</div></div>';
      if (!a.read) h += '<span class="alert-item__dot"></span>';
      h += '</div>';
    }
    h += '</div>';
    container.innerHTML = h;

    /* Wire mark-all-read button */
    var markBtn = document.getElementById("alert-mark-all-read");
    if (markBtn) markBtn.addEventListener("click", function(e) { e.stopPropagation(); markAllRead(); });

    /* Wire individual click */
    var items = container.querySelectorAll(".alert-item");
    for (var j = 0; j < items.length; j++) {
      (function(el, id) {
        el.addEventListener("click", function() { markRead(id); if (SZ.publish) SZ.publish("alert-click", id); });
      })(items[j], alerts[j].id);
    }
  }


  /* ===== UI: DROPDOWN TOGGLE ===== */
  function toggleDropdown(forceOpen) {
    var dropdown = document.getElementById("alert-dropdown");
    if (!dropdown) return;
    if (forceOpen === true) dropdown.classList.add("alert-dropdown--open");
    else if (forceOpen === false) dropdown.classList.remove("alert-dropdown--open");
    else dropdown.classList.toggle("alert-dropdown--open");
    if (dropdown.classList.contains("alert-dropdown--open")) renderList();
  }

  /* ===== UI: TOAST NOTIFICATIONS ===== */
  function showToast(type, title, description, data) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast toast--" + (type || "info").toLowerCase();
    toast.innerHTML = '<span class="toast__icon">' + getIcon(type)
      + '</span><div class="toast__body"><div class="toast__title">' + esc(title)
      + '</div><div class="toast__desc">' + esc(description)
      + '</div></div><button class="toast__close" type="button" aria-label="Fechar">&times;</button>';
    toast.dataset.alertData = JSON.stringify(data || {});
    toast.dataset.alertType = type || "info";
    container.appendChild(toast);
    void toast.offsetWidth;
    toast.classList.add("toast--visible");

    /* Close button */
    toast.querySelector(".toast__close").addEventListener("click", function(e) {
      e.stopPropagation(); dismissToast(toast);
    });

    /* Click toast body to open alert */
    toast.addEventListener("click", function(e) {
      if (e.target.closest(".toast__close")) return;
      add(type, title, description, data);
      dismissToast(toast);
      toggleDropdown(true);
    });

    /* Auto-dismiss */
    setTimeout(function() { dismissToast(toast); }, TOAST_DURATION);
  }

  function dismissToast(toast) {
    if (!toast || toast.classList.contains("toast--dismissing")) return;
    toast.classList.remove("toast--visible");
    toast.classList.add("toast--dismissing");
    setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
  }


  /* ===== EVENT INTEGRATION HOOKS ===== */

  function handleF51Block(ev) {
    var data = ev && ev.data ? ev.data : ev;
    var ticker = data.ticker || ev.ticker || (data.verdict && data.verdict.ticker) || "";
    var score = data.score != null ? data.score : (data.verdict && data.verdict.score);
    var pct = score != null ? Math.round(score * 100) : "?";
    var t = "F51 bloqueou " + (ticker || "unknown");
    var d = "Score " + pct + "% -- veredito NEGADO";
    add("GUARDRAIL", t, d, ev);
    showToast("GUARDRAIL", t, d, ev);
  }

  function handleWhaleDetection(ev) {
    var data = ev && ev.data ? ev.data : ev;
    var penny = data.pennylab || data.penny_lab || data;
    var suspicion = penny.whale_suspicion != null ? penny.whale_suspicion : (penny.scores && penny.scores.whale_suspicion);
    var ticker = data.ticker || ev.ticker || penny.ticker || "";
    if (suspicion == null || suspicion < 0.5) return;
    var s = suspicion >= 0.8 ? "FORTE" : suspicion >= 0.6 ? "MODERADO" : "FRACO";
    var t = "Baleia detectada em " + (ticker || "?") + " (" + s + ")";
    var d = "Suspicao de whale: " + Math.round(suspicion * 100) + "%";
    add("WHALE", t, d, ev);
    showToast("WHALE", t, d, ev);
  }

  function handleMangalaOpportunity(ev) {
    var data = ev && ev.data ? ev.data : ev;
    var opps = data.opportunities || (data.data && data.data.opportunities) || [];
    if (!Array.isArray(opps)) opps = [];
    var shown = 0;
    for (var i = 0; i < opps.length && shown < 3; i++) {
      var opp = opps[i];
      var ticker = opp.ticker || "?";
      var score = opp.score != null ? opp.score : "?";
      var t = "Nova oportunidade: " + ticker + " score " + score;
      var d = opp.signal || "Sinal detectado";
      add("MANGALA", t, d, opp);
      showToast("MANGALA", t, d, opp);
      shown++;
    }
  }

  function handleTradeExecuted(action, ticker, qty, price, data) {
    var t = "Paper trade executado: " + (action || "?").toUpperCase() + " " + (qty || "?") + " " + (ticker || "?");
    var d = price ? "Preco: $" + Number(price).toFixed(2) : "Trade confirmado";
    add("TRADE", t, d, data);
    showToast("TRADE", t, d, data);
  }

  function handleSystemAlert(title, description, data) {
    add("SYSTEM", title, description, data);
    showToast("SYSTEM", title, description, data);
  }


  /* ===== INIT ===== */
  function init() {
    load();
    renderBadge();
    /* Real backend alerts (read-only endpoint) + refresh every 30s. */
    hydrateFromServer();
    window.setInterval(hydrateFromServer, 30000);

    var bellBtn = document.getElementById("alert-bell-btn");
    if (bellBtn) {
      bellBtn.addEventListener("click", function(e) {
        e.stopPropagation();
        toggleDropdown();
      });
    }

    document.addEventListener("click", function(e) {
      var dd = document.getElementById("alert-dropdown");
      var btn = document.getElementById("alert-bell-btn");
      if (dd && btn && !dd.contains(e.target) && !btn.contains(e.target)) {
        dd.classList.remove("alert-dropdown--open");
      }
    });

    document.addEventListener("keydown", function(e) {
      if (e.key === "Escape") {
        var dd = document.getElementById("alert-dropdown");
        if (dd) dd.classList.remove("alert-dropdown--open");
      }
    });
  }

  /* -- Public API -- */
  window.SZ = window.SZ || {};
  window.SZ.alerts = {
    add: add,
    markRead: markRead,
    markAllRead: markAllRead,
    getUnreadCount: getUnreadCount,
    getAlerts: getAlerts,
    getServerState: getServerState,
    hydrateFromServer: hydrateFromServer,
    showToast: showToast,
    toggleDropdown: toggleDropdown,
    renderBadge: renderBadge,
    handleF51Block: handleF51Block,
    handleWhaleDetection: handleWhaleDetection,
    handleMangalaOpportunity: handleMangalaOpportunity,
    handleTradeExecuted: handleTradeExecuted,
    handleSystemAlert: handleSystemAlert,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
