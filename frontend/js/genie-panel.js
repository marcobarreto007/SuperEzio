/* SuperEzio GeniePanel */
(function () {
  "use strict";

  var SOURCE_CONFIDENCE = [
    ["NewsAPI", 0.9],
    ["Finnhub", 0.8],
    ["NewsScout", 0.7],
    ["RedditPulse", 0.5],
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }

  function num(value, digits) {
    var n = Number(value);
    if (!isFinite(n)) return "--";
    return n.toFixed(digits == null ? 2 : digits);
  }

  function labelTone(label) {
    var text = String(label || "").toUpperCase();
    if (text.indexOf("BEAR") >= 0 || text.indexOf("FEAR") >= 0 || text.indexOf("RISK") >= 0) return "is-bad";
    if (text.indexOf("BULL") >= 0 || text.indexOf("CLEAN") >= 0 || text.indexOf("POS") >= 0) return "is-good";
    return "is-warn";
  }

  function formatTime(value) {
    if (!value) return "--:--";
    var date = new Date(value);
    if (!isFinite(date.getTime())) return "--:--";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function secondsAgo(stamp) {
    if (!stamp) return "--";
    return Math.max(0, Math.round((Date.now() - stamp) / 1000)) + "s";
  }

  function cleanTicker(value) {
    if (window.SZ && typeof window.SZ.sanitTicker === "function") {
      return window.SZ.sanitTicker(value);
    }
    return String(value || "").replace(/[^A-Za-z0-9.\-]/g, "").toUpperCase().substring(0, 12);
  }

  function pulseSignalLabel(pulse) {
    var reddit = (pulse && pulse.reddit) || {};
    var news = (pulse && pulse.news) || {};
    var signal = String(reddit.signal || "").toUpperCase();
    if (signal && signal !== "NO_DATA") return reddit.signal;
    var articles = Number(news.articles || 0);
    if (articles > 0) return "NEWS " + articles;
    return "SOCIAL --";
  }

  function pulseCommand(pulse) {
    var ticker = cleanTicker(pulse && pulse.ticker);
    var sentiment = (pulse && (pulse.sentiment_display || pulse.sentiment)) || "NO_DATA";
    var score = num(pulse && pulse.score, 2);
    var reddit = (pulse && pulse.reddit) || {};
    var news = (pulse && pulse.news) || {};
    var flags = Array.isArray(pulse && pulse.flags) ? pulse.flags : [];
    var discovery = (pulse && pulse.discovery) || {};
    var discovered = !!(pulse && pulse.discovered);
    var discoveryText = discovered
      ? "Origem=DISCOVER, fonte=" + (discovery.source || "agregador") + ", query=" + (discovery.query || "--") + ", headline=" + (discovery.headline || "--") + "."
      : "Origem=watchlist fixa.";
    var parts = [
      "TICKER " + ticker + ": sincronize grafico + Sentimento Vivo.",
      "Bob, analise tese, risco, invalidacao e alvo/stop.",
      discoveryText,
      "Sentimento=" + sentiment + ", score=" + score + ", Reddit=" + (reddit.mentions || 0) + ", Noticias=" + (news.articles || 0) + ", NewsLabel=" + (news.label || "NO_DATA") + (flags.length ? ", flags=" + flags.join(", ") : "") + ".",
      "Se virar trade, rode ferramentas antes de PAPER_TICKET."
    ];
    return parts.join(" ");
  }

  function markSelectedTicker(ticker) {
    ticker = cleanTicker(ticker);
    var rows = document.querySelectorAll(".genie-pulse-card[data-genie-ticker]");
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle(
        "is-selected",
        cleanTicker(rows[i].getAttribute("data-genie-ticker")) === ticker
      );
    }
  }

  function notifyBob(pulse) {
    var ticker = cleanTicker(pulse && pulse.ticker);
    if (!ticker) return;
    var command = pulseCommand(pulse);
    var input = $("user-inp");
    if (input) {
      input.value = command;
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    var panel = $("live-panel");
    if (panel) panel.classList.remove("is-collapsed");
    var chat = $("chat");
    if (chat) {
      var cue = chat.querySelector(".bob-ticker-cue");
      if (!cue) {
        cue = document.createElement("div");
        cue.className = "bob-ticker-cue";
        chat.insertBefore(cue, chat.firstChild);
      }
      cue.innerHTML = [
        '<strong>Bob recebeu ' + esc(ticker) + '</strong>',
        '<span>Comando TICKER pronto na caixa de envio.</span>',
      ].join("");
      chat.scrollTop = 0;
    }
    window.SZ.state.pendingGenieTickerCommand = {
      ticker: ticker,
      command: command,
      pulse: pulse,
      createdAt: Date.now(),
    };
  }

  function selectPulse(pulse) {
    var ticker = cleanTicker(pulse && pulse.ticker);
    if (!ticker) return false;
    if (window.SZ && typeof window.SZ.selectTicker === "function") {
      window.SZ.selectTicker(ticker, "genie_pulse_click", {
        source: "genie",
        sentiment: pulse.sentiment || "",
        score: pulse.score,
        origin: pulse.origin || "",
        discovered: !!pulse.discovered,
        discovery: pulse.discovery || {},
      });
    } else {
      var tickerInput = $("ticker-inp");
      if (tickerInput) tickerInput.value = ticker;
    }
    markSelectedTicker(ticker);
    notifyBob(pulse);
    return true;
  }

  function pulseByTicker(ticker) {
    ticker = cleanTicker(ticker);
    var pulses = (window.SZ.state.genie && window.SZ.state.genie.pulses) || [];
    for (var i = 0; i < pulses.length; i++) {
      if (cleanTicker(pulses[i].ticker) === ticker) return pulses[i];
    }
    return null;
  }

  function renderPulse(pulses) {
    if (!Array.isArray(pulses) || pulses.length === 0) {
      return '<div class="cockpit-empty">Watchlist vazia.</div>';
    }
    return pulses.map(function (pulse) {
      var reddit = pulse.reddit || {};
      var flags = Array.isArray(pulse.flags) ? pulse.flags : [];
      var score = num(pulse.score, 2);
      var analystScore = num(pulse.analyst_score, 2);
      var sentiment = pulse.sentiment || "NO_DATA";
      var signal = pulseSignalLabel(pulse);
      var ticker = cleanTicker(pulse.ticker || "");
      var discovered = !!pulse.discovered;
      var route = discovered ? "DISCOVER" : "TICKER";
      var discovery = pulse.discovery || {};
      var selected = cleanTicker(window.SZ.state && window.SZ.state.ticker) === ticker;
      return [
        '<button class="genie-pulse-card ' + (selected ? "is-selected" : "") + '" type="button" data-genie-ticker="' + esc(ticker) + '" aria-label="Selecionar ' + esc(ticker) + ' no cockpit">',
          '<div class="genie-pulse-card__top">',
            '<strong>' + esc(ticker || pulse.ticker || "--") + '</strong>',
            '<span class="cockpit-chip ' + labelTone(sentiment) + '">' + esc(sentiment) + '</span>',
            '<span class="mono">' + score + '</span>',
            '<span class="genie-pulse-card__route">' + esc(route) + '</span>',
          '</div>',
          '<div class="genie-pulse-card__meta">',
            '<span>' + esc(reddit.mentions || 0) + ' mencoes</span>',
            '<span>' + esc(signal) + '</span>',
            '<span>rank ' + analystScore + '</span>',
          '</div>',
          (discovered && discovery.headline ? '<div class="genie-pulse-card__meta"><span>' + esc(discovery.source || "DISCOVER") + '</span><span>' + esc(discovery.headline).substring(0, 58) + '</span></div>' : ''),
          '<div class="genie-pulse-card__flags">',
            (flags.length ? flags.slice(0, 3).map(function (flag) {
              return '<span class="cockpit-chip ' + labelTone(flag) + '">' + esc(flag) + '</span>';
            }).join("") : '<span class="cockpit-chip">NO FLAGS</span>'),
          '</div>',
        '</button>',
      ].join("");
    }).join("");
  }

  function renderAlerts(alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) {
      return '<div class="cockpit-empty">Sem alertas recentes.</div>';
    }
    return alerts.slice(0, 5).map(function (alert) {
      var type = alert.type || "ALERT";
      var detail = "";
      if (type === "SPIKE") detail = esc(alert.count || "--") + " mencoes";
      else if (type === "COORD") detail = esc(alert.accounts || "--") + " contas suspeitas";
      else if (type === "SWING") detail = "delta " + esc(alert.delta || "--");
      else if (type === "DIVERGENCE") detail = "social/institucional divergente";
      return [
        '<div class="genie-alert-row">',
          '<span class="mono">' + esc(formatTime(alert.detected_at)) + '</span>',
          '<strong class="' + labelTone(type) + '">' + esc(type) + '</strong>',
          '<span>' + esc(alert.ticker || "--") + '</span>',
          '<span>' + detail + '</span>',
        '</div>',
      ].join("");
    }).join("");
  }

  function renderTimeline(pulses) {
    var rows = [];
    (pulses || []).forEach(function (pulse) {
      var news = pulse.news || {};
      if (news.label && news.label !== "NO_DATA") {
        rows.push({
          source: (pulse.sources || []).join(", ") || "sentiment",
          text: (pulse.ticker || "--") + " " + news.label + " | " + (news.articles || 0) + " artigos",
        });
      }
    });
    if (!rows.length) return '<div class="cockpit-empty">Sem manchetes novas.</div>';
    return rows.slice(0, 6).map(function (row) {
      return '<div class="genie-news-row"><span>Agora</span><strong>[' + esc(row.source) + ']</strong><span>' + esc(row.text) + '</span></div>';
    }).join("");
  }

  function renderConfidence() {
    return SOURCE_CONFIDENCE.map(function (item) {
      var pct = Math.round(item[1] * 100);
      return [
        '<div class="genie-confidence-row">',
          '<span>' + esc(item[0]) + '</span>',
          '<div class="genie-confidence-bar"><i style="width:' + pct + '%"></i></div>',
          '<strong class="mono">' + item[1].toFixed(1) + '</strong>',
        '</div>',
      ].join("");
    }).join("");
  }

  function render(data, updatedAt) {
    var body = $("genie-panel-body");
    if (!body) return;
    var pulses = (data && data.pulses) || [];
    var alerts = (data && data.alerts) || [];
    body.innerHTML = [
      '<div class="cockpit-updated">Atualizado ha <span id="genie-updated-ago">' + esc(secondsAgo(updatedAt)) + '</span></div>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Watchlist Pulse</div>' + renderPulse(pulses) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Alertas Recentes</div>' + renderAlerts(alerts) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">News Timeline</div>' + renderTimeline(pulses) + '</section>',
      '<section class="cockpit-section"><div class="cockpit-section__title">Source Confidence</div>' + renderConfidence() + '</section>',
    ].join("");
  }

  async function refresh() {
    var status = $("genie-panel-status");
    try {
      var results = await Promise.all([
        window.SZ.api.fetchSentimentPulse(),
        window.SZ.api.fetchSentimentAlerts(20),
      ]);
      var updatedAt = Date.now();
      var data = {
        pulses: results[0].pulses || [],
        alerts: results[1].alerts || [],
      };
      window.SZ.state.genie = Object.assign({}, data, { updatedAt: updatedAt });
      render(data, updatedAt);
      if (status) {
        status.textContent = "LIVE";
        status.classList.remove("cockpit-panel__status--idle");
      }
    } catch (e) {
      if (status) {
        status.textContent = "DESCONECTADO";
        status.classList.add("cockpit-panel__status--idle");
      }
      render({ pulses: [], alerts: [] }, null);
    }
  }

  function renderFromCockpit(data) {
    // Called by cockpit.js central hub with data from /cockpit/summary.genie
    var pulses = data.pulses || [];
    var alerts = data.alerts || [];
    var updatedAt = Date.now();
    window.SZ.state.genie = Object.assign(window.SZ.state.genie || {}, { pulses: pulses, alerts: alerts, updatedAt: updatedAt });
    render({ pulses: pulses, alerts: alerts }, updatedAt);
    var status = document.getElementById("genie-panel-status");
    if (status) {
      status.textContent = "LIVE";
      status.classList.remove("cockpit-panel__status--idle");
    }
  }

  function init() {
    refresh();
    var body = $("genie-panel-body");
    if (body) {
      body.addEventListener("click", function (event) {
        var card = event.target.closest(".genie-pulse-card[data-genie-ticker]");
        if (!card) return;
        selectPulse(pulseByTicker(card.getAttribute("data-genie-ticker")) || { ticker: card.getAttribute("data-genie-ticker") });
      });
    }
    window.setInterval(function () {
      var updated = window.SZ.state.genie && window.SZ.state.genie.updatedAt;
      var el = $("genie-updated-ago");
      if (el) el.textContent = secondsAgo(updated);
    }, 1000);
    window.setInterval(refresh, 30000);
  }

  window.SZ = window.SZ || {};
  window.SZ.geniePanel = { refresh: refresh, render: render, renderFromCockpit: renderFromCockpit, selectPulse: selectPulse };
  document.addEventListener("DOMContentLoaded", init);
})();
