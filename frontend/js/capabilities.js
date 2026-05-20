/* SuperEzio — Capabilities Panel */
(function () {
  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  function render(data) {
    const tasks = data?.supported_tasks || [];
    const product = data?.product || {};

    let html = `<div class="panel-grid">
      <div class="panel-tile"><span>Agent</span><strong>${esc(data?.agent || "?")}</strong></div>
      <div class="panel-tile"><span>Brain</span><strong>${esc(data?.brain || "?")}</strong></div>
    </div>`;

    html += '<div style="margin-top:10px"><h3 style="font-size:10px;color:var(--muted);text-transform:uppercase;margin-bottom:6px">Supported Tasks</h3><ul class="cap-list">';
    tasks.forEach(t => { html += `<li>${esc(t)}</li>`; });
    html += '</ul></div>';

    if (product.product_name) {
      html += `<div style="margin-top:10px;font-size:12px;color:var(--ink-secondary)">Product: ${esc(product.product_name)} — ${esc(product.positioning || "")}</div>`;
    }

    return html;
  }

  async function showPanel() {
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    pc.innerHTML = '<div style="color:var(--muted);font-size:12px;">Loading capabilities...</div>';
    try {
      const data = await SZ.api.fetchCapabilities();
      SZ.state.capabilities = data;
      pc.innerHTML = render(data);
    } catch (e) {
      pc.innerHTML = `<div style="color:var(--red);font-size:12px;">Error: ${e.message}</div>`;
    }
  }

  window.SZ.capabilities = { showPanel };
})();
