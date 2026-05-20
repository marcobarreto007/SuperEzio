/* SuperEzio — Explanation Card Renderer (Streaming) */
(function () {
  "use strict";

  var _buffer = "";
  var _card = null;
  var _finalized = false;

  function ensureCard(ceo) {
    if (_card) return _card;

    var info = SZ.cards.makeCard("Explanation", "LIVE", "neutral", "file-text");
    info.card.classList.add("card--explanation");
    info.card.classList.add("open"); // Start expanded

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
