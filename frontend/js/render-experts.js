/* SuperEzio — Expert Grid Renderer */
(function () {
  "use strict";

  var ROLES = [
    { role: "fundamental", abbr: "Fund", label: "Fundamental" },
    { role: "technical",   abbr: "Tech", label: "Technical" },
    { role: "risk",        abbr: "Risk", label: "Risk" },
    { role: "macro",       abbr: "Macro", label: "Macro" },
    { role: "quant",       abbr: "Quant", label: "Quant" },
    { role: "sentiment",   abbr: "Sent", label: "Sentiment" }
  ];

  var STATE_CLASSES = {
    running: "expert-tile--running",
    ok: "expert-tile--ok",
    fail: "expert-tile--fail",
    skip: "expert-tile--skip",
    pending: "expert-tile--pending"
  };

  function stateIcon(state) {
    if (state === "running") return "⟳";
    if (state === "ok") return "✓";
    if (state === "fail") return "✗";
    if (state === "skip") return "—";
    return "○";
  }

  function stateColor(state) {
    if (state === "running") return "var(--amber)";
    if (state === "ok") return "var(--green)";
    if (state === "fail") return "var(--red)";
    if (state === "skip") return "var(--muted)";
    return "var(--muted)";
  }

  /* Freshness stamp — implemented in render-pipeline.js (loaded first).
   * Resolved at call time so script order is irrelevant. */
  function stampCard(card, ev, label) {
    if (SZ.stamp && SZ.stamp.card) SZ.stamp.card(card, ev, label);
  }

  function makeTile(roleObj) {
    var tile = SZ.dom.el("div", "expert-tile expert-tile--pending");
    tile.setAttribute("data-role", roleObj.role);

    var abbr = SZ.dom.el("span", "expert-tile__abbr");
    abbr.textContent = roleObj.abbr;
    tile.appendChild(abbr);

    var label = SZ.dom.el("span", "expert-tile__label");
    label.textContent = roleObj.label;
    tile.appendChild(label);

    var icon = SZ.dom.el("span", "expert-tile__icon");
    icon.textContent = stateIcon("pending");
    icon.style.color = stateColor("pending");
    tile.appendChild(icon);

    var provider = SZ.dom.el("span", "expert-tile__provider");
    provider.textContent = "";
    tile.appendChild(provider);

    return tile;
  }

  function initCard(ceo) {
    var done = 0;
    var total = ROLES.length;
    var badgeText = done + "/" + total;

    var info = SZ.cards.makeCard("Expert Analysis", badgeText, "neutral", "users");
    info.card.classList.add("card--experts");


    var grid = SZ.dom.el("div", "expert-grid");

    ROLES.forEach(function (roleObj) {
      var tile = makeTile(roleObj);
      grid.appendChild(tile);
    });

    info.body.appendChild(grid);

    // Store reference for updates
    info._expertTiles = {};
    grid.querySelectorAll(".expert-tile").forEach(function (tile) {
      info._expertTiles[tile.getAttribute("data-role")] = tile;
    });
    info._doneCount = 0;

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

    // Stamp AFTER insertion. EXPERT_STARTED / EXPERT_DONE /
    // EXPERT_SKIPPED carry only role+provider
    // (src/core/pipeline/nodes/experts.py:546, :573, :620) -> receipt
    // clock, refreshed on every tile update in updateTile().
    stampCard(info.card, null, "EXPERT_*");

    return info;
  }

  function updateTile(role, status, ceo) {
    // Find or create card
    var card = ceo.bubble.querySelector(".card--experts");
    var info;
    if (!card) {
      info = initCard(ceo);
      card = info.card;
    }

    var tile = card.querySelector('[data-role="' + role + '"]');
    if (!tile) return;

    // Every expert event advances the card's clock: the grid state is
    // exactly as fresh as the last event that touched it.
    stampCard(card, null, "EXPERT_" + String(status || "").toUpperCase());

    var wasRunning = tile.classList.contains("expert-tile--running");
    var isNowDone = (status === "ok" || status === "fail" || status === "skip");

    // Remove all state classes
    Object.values(STATE_CLASSES).forEach(function (cls) {
      tile.classList.remove(cls);
    });
    tile.classList.add(STATE_CLASSES[status] || STATE_CLASSES.pending);

    var icon = tile.querySelector(".expert-tile__icon");
    if (icon) {
      icon.textContent = stateIcon(status);
      icon.style.color = stateColor(status);
      if (status === "running") {
        icon.classList.add("pulse");
      } else {
        icon.classList.remove("pulse");
      }
    }

    // Update badge count
    if (wasRunning && isNowDone) {
      var badge = card.querySelector(".card-badge");
      if (badge) {
        var parts = badge.textContent.split("/");
        var done = parseInt(parts[0], 10) || 0;
        done++;
        badge.textContent = done + "/" + ROLES.length;

        // Update badge class based on progress
        if (done === ROLES.length) {
          var allOk = !card.querySelector(".expert-tile--fail");
          badge.className = "card-badge card-badge--" + (allOk ? "pass" : "fail");
        }
      }
    }
  }

  window.SZ.renderExperts = {
    initCard: initCard,
    updateTile: updateTile
  };
})();
