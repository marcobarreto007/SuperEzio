/* SuperEzio — Frontend content and defaults */
(function () {
  window.SZ = window.SZ || {};

  window.SZ.config = Object.assign({
    defaultTicker: "",
    defaultTimeframe: "6M",
    hiddenAuditTickers: ["AAPL"],
    showDebugCards: false,
  }, window.SZ.config || {});

  window.SZ.content = Object.assign({
    logoSub: "Financial Copilot",
    statusChecking: "Checking...",
    chartContextPlaceholder: "Chart",
    assetLabel: "Market snapshot",
    bobWelcomeTitle: "Bob is online.",
    bobWelcomeBody: "Ask directly. Market context is attached when your question needs the chart.",
    sdcaReady: "Ready for local firewall evaluation.",
    sdcaPresetFomo: "FOMO preset",
    sdcaPresetSafe: "Conservative preset",
    loading: "Loading...",
    ops: {
      status: "Status",
      gpu: "GPU Acceleration",
      redis: "Redis Database",
      ceo: "Local Model (CEO)",
      capabilities: "Agent Capabilities",
      manifest: "Product Manifest & Principles",
      principles: "Operating Principles:",
    },
  }, window.SZ.content || {});

  window.SZ.sdcaPresets = Object.assign({
    fomo: {
      id: "lab-fomo-001",
      source: "manual",
      asset: "BTC-CAD",
      action: "buy_leveraged",
      amount: "500",
      thesis: "BTC moved hard and I want to enter now before it runs away.",
      priceChange: "7.2",
      latency: "high",
      spread: "wide",
      hype: "high",
      dataQuality: "low",
      fomo: true,
      leverage: true,
      slippage: true,
      stale: true,
    },
    safe: {
      id: "lab-safe-001",
      source: "operator",
      asset: "CASH",
      action: "hold_cash",
      amount: "50",
      thesis: "Small conservative decision with low execution risk and stable evidence.",
      priceChange: "0.2",
      latency: "low",
      spread: "tight",
      hype: "low",
      dataQuality: "high",
      fomo: false,
      leverage: false,
      slippage: false,
      stale: false,
    },
  }, window.SZ.sdcaPresets || {});
})();
