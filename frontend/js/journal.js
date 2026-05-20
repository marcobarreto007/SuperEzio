/* SuperEzio — Journal Panel */
(function () {
  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  function load() {
    try { return JSON.parse(localStorage.getItem("superezio.journal") || "[]"); }
    catch { return []; }
  }

  function render(entries) {
    if (!entries.length) return '<div style="color:var(--muted);font-size:12px;padding:8px">No journal entries yet.</div>';

    let html = '<div class="journal-list">';
    entries.slice(0, 30).forEach((e, i) => {
      const time = e.at ? new Date(e.at).toLocaleString() : "?";
      const preview = (e.prompt || e.answer || "").slice(0, 80);
      html += `<div class="journal-entry" data-idx="${i}">
        <div class="je-time">${esc(time)}</div>
        ${e.ticker ? `<span class="je-ticker">${esc(e.ticker)}</span>` : ""}
        <div class="je-preview">${esc(preview)}</div>
      </div>`;
    });
    html += '</div>';
    html += '<div style="margin-top:8px"><button class="btn--sm" id="journal-clear">Clear journal</button></div>';
    return html;
  }

  function showPanel() {
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    const entries = load();
    SZ.state.journal = entries;
    pc.innerHTML = render(entries);

    // Wire clear button
    const clearBtn = document.getElementById("journal-clear");
    if (clearBtn) clearBtn.addEventListener("click", () => {
      localStorage.removeItem("superezio.journal");
      SZ.state.journal = [];
      pc.innerHTML = render([]);
    });

    // Wire entry clicks to expand
    pc.querySelectorAll(".journal-entry").forEach(el => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.dataset.idx || "0");
        const entry = entries[idx];
        if (!entry) return;
        const full = entry.answer || entry.prompt || "";
        const existing = el.querySelector(".je-full");
        if (existing) { existing.remove(); return; }
        const div = document.createElement("div");
        div.className = "je-full";
        div.style.cssText = "font-size:11px;color:var(--ink-secondary);margin-top:6px;white-space:pre-wrap;max-height:200px;overflow-y:auto";
        div.textContent = full;
        el.appendChild(div);
      });
    });
  }

  window.SZ.journal = { showPanel, load };
})();
