/* SuperEzio — Chat DOM */
(function () {
  const CHAT = document.getElementById("chat");
  let currentCEO = null;

  function el(tag, cls, attrs = {}) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "text") e.textContent = v;
      else if (k === "html") e.innerHTML = v;
      else e.setAttribute(k, v);
    });
    return e;
  }

  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }

  function stripThink(t) {
    return (t || "").replace(/<think[\s\S]*?<\/think>/gi, "").replace(/<think[\s\S]*$/gi, "");
  }

  function addMessage(role) {
    const msg = el("div", "msg msg-" + role);
    const bubble = el("div", "msg-bubble");
    const meta = el("div", "msg-meta");
    meta.innerHTML = `<span>${role === "user" ? "You" : "Bob CEO"}</span><span>${new Date().toLocaleTimeString()}</span>`;
    msg.append(bubble, meta);
    CHAT.appendChild(msg);
    return { msg, bubble, meta, cards: new Map() };
  }

  function ensureCEOMessage() {
    if (!currentCEO || currentCEO.msg.dataset.done === "1") {
      currentCEO = addMessage("ceo");
      currentCEO.msg.dataset.done = "0";
      const think = el("div", "thinking");
      think.innerHTML = "<span></span><span></span><span></span>";
      currentCEO.bubble.appendChild(think);
      currentCEO._think = think;
    }
    return currentCEO;
  }

  function finishCEOMessage() {
    if (!currentCEO) return;
    currentCEO.msg.dataset.done = "1";
    if (currentCEO._think) { currentCEO._think.remove(); currentCEO._think = null; }
  }

  function appendChunk(text) {
    const ceo = ensureCEOMessage();
    if (ceo._think) { ceo._think.remove(); ceo._think = null; }
    SZ.state.stream.answer += text || "";
    const clean = stripThink(SZ.state.stream.answer);
    ceo.bubble.childNodes.forEach(n => {
      if (n.nodeType === 3 || (n.nodeType === 1 && !n.classList.contains("card") && !n.classList.contains("pipeline-bar") && !n.classList.contains("thinking")))
        n.remove();
    });
    const textNode = document.createTextNode(clean);
    const firstExtra = ceo.bubble.querySelector(".card, .pipeline-bar");
    if (firstExtra) ceo.bubble.insertBefore(textNode, firstExtra);
    else ceo.bubble.appendChild(textNode);
    ceo.bubble.normalize();
  }

  window.SZ.chat = { addMessage, ensureCEOMessage, finishCEOMessage, appendChunk, el, esc, stripThink, get currentCEO() { return currentCEO; }, set currentCEO(v) { currentCEO = v; } };
  window.SZ.esc = esc;
  window.SZ.dom = { el, esc };
})();
