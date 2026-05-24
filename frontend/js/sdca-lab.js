/* SuperEzio — SDCA Lab */
(function () {
  const PRESETS = {
    fomo: {
      id: "lab-fomo-001", source: "manual", asset: "BTC-CAD", action: "buy_leveraged", amount: "500",
      thesis: "BTC moved hard and I want to enter now before it runs away.",
      priceChange: "7.2", latency: "high", spread: "wide", hype: "high", dataQuality: "low",
      fomo: true, leverage: true, slippage: true, stale: true,
    },
    safe: {
      id: "lab-safe-001", source: "operator", asset: "CASH", action: "hold_cash", amount: "50",
      thesis: "Small conservative decision with low execution risk and stable evidence.",
      priceChange: "0.2", latency: "low", spread: "tight", hype: "low", dataQuality: "high",
      fomo: false, leverage: false, slippage: false, stale: false,
    },
  };

  function $(id) { return document.getElementById(id); }

  function numOrNull(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }

  function setPreset(kind) {
    const p = PRESETS[kind] || PRESETS.fomo;
    $("sdca-id").value = p.id; $("sdca-source").value = p.source;
    $("sdca-asset").value = p.asset; $("sdca-action").value = p.action;
    $("sdca-amount").value = p.amount; $("sdca-thesis").value = p.thesis;
    $("sdca-price-change").value = p.priceChange; $("sdca-latency").value = p.latency;
    $("sdca-spread").value = p.spread; $("sdca-hype").value = p.hype;
    $("sdca-data-quality").value = p.dataQuality;
    $("sdca-fomo").checked = p.fomo; $("sdca-leverage").checked = p.leverage;
    $("sdca-slippage").checked = p.slippage; $("sdca-stale").checked = p.stale;
  }

  function buildCandidate() {
    return {
      id: $("sdca-id").value.trim() || `lab-${Date.now()}`,
      source: $("sdca-source").value || "manual",
      asset: $("sdca-asset").value.trim() || null,
      action: $("sdca-action").value.trim() || "review_decision",
      thesis: $("sdca-thesis").value.trim() || "Manual SDCA lab evaluation.",
      amount_cad: numOrNull($("sdca-amount").value),
      risk_context: {
        fomo: $("sdca-fomo").checked, leverage: $("sdca-leverage").checked,
        latency: $("sdca-latency").value, data_quality: $("sdca-data-quality").value,
        stale_signal: $("sdca-stale").checked, execution_slippage_risk: $("sdca-slippage").checked,
      },
      raw_signals: {
        price_change_2h: numOrNull($("sdca-price-change").value),
        social_hype: $("sdca-hype").value, spread: $("sdca-spread").value,
        slippage_risk: $("sdca-slippage").checked ? "high" : "low",
      },
      timestamp: new Date().toISOString(),
    };
  }

  function esc(v) { return String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  function pct(v) { return v != null ? Math.round(v * 100) + "%" : "--"; }
  function fmt(v, d = 2) { return v != null && isFinite(v) ? Number(v).toLocaleString("en-US", { maximumFractionDigits: d }) : "--"; }

  function renderResult(result) {
    const d = String(result?.decision || "REVIEW");
    const score = result?.consequence_score || {};
    const tokens = Array.isArray(result?.ghost_tokens) ? result.ghost_tokens : [];
    const matches = Array.isArray(result?.matched_experiences) ? result.matched_experiences : [];
    const trace = Array.isArray(result?.rumination_trace) ? result.rumination_trace : [];
    const audit = result?.audit_log || {};
    const R = $("sdca-result");
    R.innerHTML = `
      <div class="sdca-lab-decision"><strong>${esc(d)}</strong><span class="${esc(d.toLowerCase())}">${esc(d.toLowerCase())}</span></div>
      <div class="sdca-summary">${esc(result?.human_summary || "No summary returned.")}</div>
      <div class="sdca-metrics">
        <div class="sdca-metric"><span>Confidence</span><strong>${pct(result?.confidence)}</strong></div>
        <div class="sdca-metric"><span>Uncertainty</span><strong>${pct(result?.uncertainty)}</strong></div>
        <div class="sdca-metric"><span>Utility</span><strong>${pct(score.utility)}</strong></div>
        <div class="sdca-metric"><span>Revenue Risk</span><strong>${pct(score.revenue_risk)}</strong></div>
        <div class="sdca-metric"><span>Truth</span><strong>${pct(score.truthfulness)}</strong></div>
        <div class="sdca-metric"><span>Cost Risk</span><strong>${pct(score.cost_risk)}</strong></div>
      </div>
      <div class="sdca-lab-section"><h3>Ghost Tokens</h3><div class="sdca-token-row">${tokens.slice(0, 12).map(t => `<span class="sdca-token">${esc(t)}</span>`).join("") || '<span class="sdca-token">none</span>'}</div></div>
      <div class="sdca-lab-section"><h3>Matched Experiences</h3><div class="sdca-lab-list">${matches.slice(0, 3).map(m => `<div><strong>${esc(m.episode_id)}</strong><br>${esc(m.learned_rule || m.consequence || "")}<br><span>score ${fmt(m.weighted_score, 3)} | delta ${fmt(m.delta_r, 2)}</span></div>`).join("") || "<div>No experience match returned.</div>"}</div></div>
      <div class="sdca-lab-section"><h3>Rumination</h3><div class="sdca-lab-list">${trace.map(r => `<div>Cycle ${esc(r.cycle)}: ${esc(r.status)} | uncertainty ${pct(r.uncertainty)} | delta ${r.delta_u == null ? "--" : fmt(r.delta_u, 3)}</div>`).join("") || "<div>No rumination trace returned.</div>"}</div></div>
      <div class="sdca-lab-section"><h3>Audit</h3>
        <div class="sdca-lab-row"><span>No Broker Execution</span><strong>${audit.no_broker_execution === true ? "true" : "false"}</strong></div>
        <div class="sdca-lab-row"><span>No External API Calls</span><strong>${audit.no_external_api_calls === true ? "true" : "false"}</strong></div>
      </div>`;
    if (window.lucide) lucide.createIcons();
  }

  async function run() {
    const candidate = buildCandidate();
    const btn = $("sdca-run-btn");
    btn.disabled = true;
    $("sdca-result").innerHTML = '<div class="sdca-lab-empty">Evaluating...</div>';
    try {
      const result = await SZ.api.evaluateSDCA(candidate);
      renderResult(result);
    } catch (e) {
      $("sdca-result").innerHTML = `<div class="sdca-lab-empty" style="color:var(--red)">Error: ${esc(e.message)}</div>`;
    } finally { btn.disabled = false; }
  }

  function toggle(open) {
    const lab = $("sdca-lab");
    if (!lab) return;

    const action = () => {
      try {
        const isVisible = lab.matches(":popover-open");
        const next = open ?? !isVisible;
        if (next) {
          lab.showPopover();
          lab.classList.add("open");
          // Auto-close Ops Console if open
          const ops = document.getElementById("ops-console");
          if (ops && ops.matches(":popover-open")) {
            ops.hidePopover();
            ops.classList.remove("open");
          }
        } else {
          lab.hidePopover();
          lab.classList.remove("open");
        }
      } catch (e) {
        // Fallback for older environments
        const next = open ?? !lab.classList.contains("open");
        lab.classList.toggle("open", next);
      }
    };

    if (document.startViewTransition) {
      document.startViewTransition(action);
    } else {
      action();
    }
  }

  window.SZ.sdcaLab = { toggle, setPreset, run };

  const form = $("sdca-form");
  if (form) {
    form.addEventListener("submit", ev => {
      ev.preventDefault();
      run();
    });
  }
  const runBtn = $("sdca-run-btn");
  if (runBtn) runBtn.addEventListener("click", run);
  const fomoBtn = $("sdca-preset-fomo");
  if (fomoBtn) fomoBtn.addEventListener("click", () => setPreset("fomo"));
  const safeBtn = $("sdca-preset-safe");
  if (safeBtn) safeBtn.addEventListener("click", () => setPreset("safe"));
})();
