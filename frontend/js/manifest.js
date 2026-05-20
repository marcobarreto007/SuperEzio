/* SuperEzio — Manifest Panel */
(function () {
  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

  function render(data) {
    const committee = data?.committee || {};
    const fast = committee.fast_mode || {};
    const full = committee.full_mode || {};
    const penny = data?.penny_guardrail || {};
    const workflow = data?.workflow || [];
    const modes = data?.decision_modes || [];
    const principles = data?.operating_principles || [];
    const actions = data?.safe_actions || [];
    const runtime = data?.runtime || {};

    let html = '';

    // Product info
    html += `<div class="manifest-section"><h3>Product</h3>
      <div style="font-size:14px;font-weight:700;margin-bottom:4px">${esc(data?.product_name || "?")}</div>
      <div style="font-size:12px;color:var(--ink-secondary)">${esc(data?.positioning || "")}</div>
    </div>`;

    // Committee modes
    html += `<div class="manifest-section"><h3>Fast Mode — ${esc(fast.label || "?")} (${fast.agent_count || "?"} agents)</h3>
      <div class="manifest-roles">${(fast.roles || []).map(r => `<span class="manifest-role">${esc(r)}</span>`).join("")}</div></div>`;

    html += `<div class="manifest-section"><h3>Full Mode — ${esc(full.label || "?")} (${full.agent_count || "?"} agents)</h3>
      <div class="manifest-roles">${(full.roles || []).map(r => `<span class="manifest-role">${esc(r)}</span>`).join("")}</div></div>`;

    html += `<div class="manifest-section"><h3>PennyLab Guardrail (${penny.agent_count || "?"} agents)</h3>
      <div class="manifest-roles">${(penny.roles || []).map(r => `<span class="manifest-role">${esc(r)}</span>`).join("")}</div></div>`;

    // Workflow
    html += `<div class="manifest-section"><h3>Workflow</h3><div class="manifest-workflow">${workflow.map((w, i) => `<div class="manifest-step"><strong>${esc(w.label || w.id)}</strong><span>${esc(w.description || "")}</span></div>${i < workflow.length - 1 ? '<span style="color:var(--line)">→</span>' : ''}`).join("")}</div></div>`;

    // Safe actions
    html += `<div class="manifest-section"><h3>Safe Actions</h3><div class="manifest-roles">${actions.map(a => `<span class="manifest-role" style="background:var(--green-bg);color:var(--green);border-color:var(--green-dim)">${esc(a)}</span>`).join("")}</div></div>`;

    // Decision modes
    html += `<div class="manifest-section"><h3>Decision Modes</h3><div class="manifest-roles">${modes.map(m => `<span class="manifest-role">${esc(m)}</span>`).join("")}</div></div>`;

    // Principles
    if (principles.length) {
      html += `<div class="manifest-section"><h3>Operating Principles</h3><ul style="list-style:none;padding:0">${principles.map(p => `<li style="font-size:11px;color:var(--ink-secondary);padding:3px 0;border-bottom:1px solid var(--line)">${esc(p)}</li>`).join("")}</ul></div>`;
    }

    // Runtime
    const rs = runtime?.status || {};
    if (rs.mode) {
      html += `<div class="manifest-section"><h3>Runtime</h3><div class="panel-grid">
        <div class="panel-tile"><span>Brain</span><strong>${esc(runtime?.brain || rs.mode || "?")}</strong></div>
        <div class="panel-tile"><span>Nodes</span><strong>${Array.isArray(rs.nodes) ? rs.nodes.length : "?"}</strong></div>
        <div class="panel-tile panel-tile--${rs.gateway_available ? 'ok' : 'warn'}"><span>Gateway</span><strong>${rs.gateway_available ? "OK" : "DOWN"}</strong></div>
      </div></div>`;
    }

    return html;
  }

  async function showPanel() {
    const pc = document.getElementById("panel-content");
    if (!pc) return;
    pc.innerHTML = '<div style="color:var(--muted);font-size:12px;">Loading manifest...</div>';
    try {
      const data = await SZ.api.fetchManifest();
      SZ.state.manifest = data;
      pc.innerHTML = render(data);
    } catch (e) {
      pc.innerHTML = `<div style="color:var(--red);font-size:12px;">Error: ${e.message}</div>`;
    }
  }

  window.SZ.manifest = { showPanel };
})();
