/* SuperEzio — Explanation Card Renderer (Streaming) */
(function () {
  "use strict";

  var _buffer = "";
  var _card = null;
  var _finalized = false;

  /* Freshness stamp — implemented in render-pipeline.js (loaded first).
   * Resolved at call time so script order is irrelevant. */
  function stampCard(card, ev, label) {
    if (SZ.stamp && SZ.stamp.card) SZ.stamp.card(card, ev, label);
  }

  function ensureCard(ceo) {
    if (_card && _card.card && _card.card.isConnected) return _card;
    _card = null;
    ceo = ceo || (SZ.chat && SZ.chat.currentCEO);
    if (!ceo || !ceo.bubble) return null;

    var info = SZ.cards.makeCard("Explanation", "LIVE", "neutral", "file-text");
    info.card.classList.add("card--explanation");
    info.setOpen(true);

    var content = SZ.dom.el("div", "explanation-content");
    content.style.whiteSpace = "pre-wrap";
    content.style.wordBreak = "break-word";
    content.style.lineHeight = "1.6";
    content.style.color = "var(--ink)";
    content.style.fontSize = "0.9em";
    content.textContent = "";
    info.body.appendChild(content);

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

    _card = info;
    return info;
  }

  function accumulate(text, ceo) {
    if (_finalized) return;

    _buffer += text || "";
    var info = ensureCard(ceo);
    if (!info) return null;

    // EXPLANATION_CHUNK carries only `content` (no timestamp), so the
    // clock is receipt time — and it is re-stamped on every chunk, which
    // means it goes quiet the moment the stream dies.
    stampCard(info.card, null, "EXPLANATION_CHUNK");

    var content = info.body.querySelector(".explanation-content");
    if (content) {
      content.textContent = _buffer;
    }

    // Update badge to show accumulating state
    var badge = info.card.querySelector(".card-badge");
    if (badge) {
      var charCount = _buffer.length;
      if (charCount > 1000) {
        badge.textContent = (charCount / 1000).toFixed(1) + "K chars";
      } else {
        badge.textContent = charCount + " chars";
      }
    }

    return info;
  }

  function finalize(ceo) {
    if (_finalized) return;
    _finalized = true;

    var info = ensureCard(ceo);
    if (!info) return null;

    stampCard(info.card, null, "EXPLANATION_FINAL");

    var content = info.body.querySelector(".explanation-content");
    if (content) {
      content.textContent = _buffer;
    }

    // Update badge to DONE
    var badge = info.card.querySelector(".card-badge");
    if (badge) {
      badge.textContent = "DONE";
      badge.classList.remove("card-badge--neutral");
      badge.classList.add("card-badge--pass");
    }

    // Reset internal state for next CEO message
    _buffer = "";
    _card = null;
    _finalized = false;

    return info;
  }

  window.SZ.renderExplanation = {
    accumulate: accumulate,
    finalize: finalize
  };
})();
