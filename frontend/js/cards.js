/* SuperEzio — Card Factory */
(function () {
  function makeCard(title, badgeText, badgeClass, icon) {
    const c = SZ.dom.el("div", "card");
    const hdr = SZ.dom.el("div", "card-hdr");
    hdr.setAttribute("role", "button");
    hdr.setAttribute("tabindex", "0");
    hdr.setAttribute("aria-expanded", "false");

    const titleWrap = SZ.dom.el("span", "card-title");
    titleWrap.innerHTML = `<i data-lucide="${icon || 'info'}" class="card-icon"></i> ${SZ.esc(title)}`;
    hdr.appendChild(titleWrap);

    const badge = SZ.dom.el("span", "card-badge card-badge--" + (badgeClass || "neutral"));
    badge.textContent = badgeText || "--";
    hdr.appendChild(badge);

    const closeBtn = SZ.dom.el("button", "card-close");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close " + title);
    closeBtn.setAttribute("title", "Close");
    closeBtn.innerHTML = '<i data-lucide="x"></i>';
    hdr.appendChild(closeBtn);

    const body = SZ.dom.el("div", "card-body");
    c.append(hdr, body);

    function setOpen(next) {
      c.classList.toggle("open", next);
      hdr.setAttribute("aria-expanded", next ? "true" : "false");
    }

    function toggleOpen() {
      setOpen(!c.classList.contains("open"));
    }

    hdr.addEventListener("click", toggleOpen);
    hdr.addEventListener("keydown", ev => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        toggleOpen();
      }
    });
    closeBtn.addEventListener("click", ev => {
      ev.preventDefault();
      ev.stopPropagation();
      c.dispatchEvent(new CustomEvent("sz:card-closed", { detail: { title } }));
      c.remove();
    });
    return { card: c, body, badge, hdr, closeBtn, setOpen };
  }

  window.SZ.cards = { makeCard };
})();
