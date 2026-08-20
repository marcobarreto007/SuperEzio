# Final Packaging Plan

> **HISTORICAL / SUPERSEDED.** This plan preserves an earlier packaging snapshot and references artifacts and broker boundaries that are no longer authoritative. Do not use it as a delivery checklist. Use `README.md`, `docs/runbooks/RUNBOOK.md`, and `docs/runbooks/DELIVERY_CHECKLIST_v3.md`.

Objective: package SuperEzio Financeiro as a buyer-ready AI financial copilot for small investors, while preserving the deeper technical system as an advanced trust layer.

## Product Position

SuperEzio should not be packaged as a trading bot or registered advisor.

The buyer-facing sentence:

> SuperEzio is a local-first AI financial research copilot that helps a small investor ask better questions, inspect evidence, understand risk, and decide what to study, watch, wait on, or avoid.

Core promise:

- complex engine underneath
- simple first interaction
- no broker execution
- no profit guarantee
- no fake cards
- every visible status either has real data or is clearly labelled as unavailable/not required

## Packaging Gate

Before listing, every first-screen element must pass this test:

1. What user question does it answer?
2. What real endpoint, local state, or user action feeds it?
3. What happens if the data is missing?
4. Does the wording make a small investor more confident or more afraid?
5. Is it buyer-facing or operator-only?

If an element cannot answer these five questions, remove it, hide it behind advanced mode, or rewrite it.

## Frontpage Information Architecture

Recommended first-screen hierarchy:

1. Ask Bob
   - Primary surface.
   - Natural-language input.
   - Final verdict and explanation visible.
   - No debug cards by default.

2. Market Snapshot
   - Ticker, timeframe, last price, change, company profile, chart.
   - Honest mode label: snapshot unless live stream is actively running.

3. Trust Layer
   - Small status indicator only on the first screen.
   - Detailed Ops Console hidden behind an icon.
   - SDCA/risk firewall hidden behind an icon or labelled as risk check.

4. Advanced Evidence
   - Only shown when the buyer/user asks for details.
   - Pipeline, experts, F51, SDCA, provider logs, and diagnostics.

## Buyer Package

Create these files/artifacts before listing:

- `SELLER_ONE_PAGER.md`: what it is, who it serves, what is included.
- `DEMO_SCRIPT.md`: exact 5-8 minute demo flow.
- `SETUP_GUIDE_WINDOWS.md`: fresh-machine install and first successful run.
- `TRANSFER_CHECKLIST.md`: source, model path, API keys, ports, dependencies, local-only policy.
- `EVIDENCE_INDEX.md`: tests, browser smoke, screenshots, checkpoints, API proof.
- `RISK_DISCLOSURE.md`: not financial advice, no broker execution, regulatory limits, data provider dependencies.
- `ARCHITECTURE_ONE_PAGER.md`: Bob, DataHub, pipeline, SDCA, providers, frontend.

## Demo Script

Demo should prove trust, not complexity:

1. Start services.
2. Open UI.
3. Show health dot online.
4. Show AAPL chart snapshot and profile.
5. Ask a CAD 25k allocation question.
6. Show final verdict and disclaimer.
7. Ask a chart-aware prompt using RSI/MACD.
8. Open risk firewall briefly and run a conservative preset.
9. Open Ops Console briefly to show GPU/local orchestrator/capabilities.
10. Close with transferability: local runtime, source code, docs, tests.

## Visual Rule

The interface may look sophisticated, but it must not look dangerous.

Use:

- precise labels
- visible disclaimers in answers
- subdued status indicators
- clear separation between investor mode and operator mode
- no decorative cards
- no scary offline labels for optional services
- no unexplained internal acronyms on the primary surface

## Exit Readiness

Ready to list only when:

- full UI smoke with chat passes
- frontpage correspondence audit passes
- setup guide works on a clean machine or VM
- demo video exists
- evidence index links to current artifacts
- transfer checklist is complete
- asking price and reserve are written down before negotiations
