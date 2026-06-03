# Frontpage Correspondence Audit - 2026-06-03

Scope: verify whether the visible SuperEzio frontpage corresponds to real data, real actions, and real backend contracts before packaging the product for a small-investor buyer.

## Verdict

Pass after targeted fixes.

The frontpage now has a defensible A-to-B contract:

- AAPL selected in the ticker input maps to the workspace header, chart fetch, price strip, chart canvas, and chart-aware prompt context.
- A general allocation prompt does not leak the visible chart ticker into the backend payload.
- A chart-specific prompt attaches the visible ticker and chart context.
- Ops Console and SDCA Lab are not decorative: both call real endpoints and return real values.
- Debug cards are off by default, keeping the small-investor surface simple.

## Evidence

Command:

```powershell
python -u scripts/browser_smoke.py --timeout-ms 360000
```

Result:

- health: ok
- chart_fetch: AAPL, 130 candles
- canvas: nonBlank 378108
- chat: finalContentLength 2298
- detectedIntent: CAPITAL_ALLOCATION
- scannerInvoked: false
- fallbackUsed: false
- containsFinalVerdict: true
- console_errors: []
- screenshot: `output/playwright/superezio-browser-smoke-20260603-091024.png`

Additional payload audit:

- Generic prompt: `ticker=""`, `chart_context.length=0`
- Chart prompt: `ticker="AAPL"`, `chart_context.length=232`
- Chart context includes RSI and MACD
- Live mode label: `SNAPSHOT`
- Profile bar: `Apple Inc | NASDAQ NMS - GLOBAL MARKET | 4.6T | USD`
- First-screen labels: `Financial Copilot`, `Bob Copilot`, `Market snapshot`
- Welcome panel removed after first user message; no first-message overlap in the final screenshot
- Ops Console: status OK, GPU visible, Redis shown as not required, local orchestrator configured
- SDCA Lab: returns REVIEW with no broker execution and no external API calls

## Fixes Applied

- `frontend/js/content.js`: debug cards disabled by default.
- `frontend/index.html`: chart status label changed from misleading stream/off state to snapshot mode.
- `frontend/js/init.js`: chart context now reads `profile` as well as `meta`, and reads flat indicator series for RSI/MACD/SMA/EMA.
- `frontend/js/render-profile.js`: profile bar now renders backend `profile` data.
- `frontend/js/live.js`: stopped stream state now says `SNAPSHOT`, not `OFF`.
- `frontend/js/ops-console.js`: Redis skipped is shown as not required; local orchestrator configuration no longer appears as CEO offline.
- `frontend/index.html`, `frontend/js/content.js`, `frontend/js/chat.js`: buyer-facing labels now use `Financial Copilot`, `Bob Copilot`, and `Market snapshot` instead of more internal operator language.
- `frontend/js/init.js`: the welcome panel is removed once the first user message starts, preventing visual overlap.

## Remaining UX Risk

The product still exposes internal language such as `SDCA` and `System Operations Control` inside advanced drawers. These are true to the architecture, but they may feel too operational for a small investor if surfaced too early.

Packaging should present the first screen as a financial copilot, with advanced/system language treated as an operator layer.
