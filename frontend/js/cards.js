/* SuperEzio — Card Factory */
(function () {
  function makeCard(title, badgeText, badgeClass, icon) {
    const c = SZ.dom.el("div", "card");
    const hdr = SZ.dom.el("div", "card-hdr");
    hdr.innerHTML = `<i data-lucide="${icon || 'info'}" class="card-icon"></i> ${SZ.esc(title)}`;
    const badge = SZ.dom.el("span", "card-badge card-badge--" + (badgeClass || "neutral"));
    badge.textContent = badgeText || "--";
    hdr.appendChild(badge);
    const body = SZ.dom.el("div", "card-body");
    c.append(hdr, body);
    hdr.addEventListener("click", () => { c.classList.toggle("open"); });
    return { card: c, body, badge, hdr };
  }

  window.SZ.cards = { makeCard };
})();
