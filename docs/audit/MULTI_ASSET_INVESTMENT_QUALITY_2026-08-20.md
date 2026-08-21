# Multi-Asset Investment Quality Audit — 2026-08-20

## Verdict

**INVESTMENT SKILL NOT PROVEN.** SuperEzio remains a research copilot. The current
evidence does not support claims that its directional model or trading strategy beats
market benchmarks, and it must not be used to justify real-capital automation.

## Why the old AAPL evidence was invalid

The previous live gate repeatedly used AAPL and reported a response-form score of 0.87.
That score measured text length, structure and numeric density when the optional reward
model was unavailable. It did not measure forecast accuracy, return, drawdown or alpha.

AAPL was also privileged in the DataHub health probe, active prompt examples, a portfolio
fallback, the browser E2E and the only expensive live ticker integration. Those couplings
have been removed. AAPL remains analyzable only when the user explicitly requests it.

## Real multi-asset evaluation

Command executed:

```powershell
python scripts/evaluate_investment_quality.py --output output/evals/investment_quality_20260820.json
```

Exploratory universe: SPY, QQQ, IWM, RY.TO, XIU.TO, GLD, TLT and BTC-USD. This covers US
large-cap, growth and small-cap equities, Canadian equity/ETF, gold, long Treasuries and
crypto. AAPL is absent by design. Horizons were 1, 5 and 20 daily bars, producing 24 cases.
The matrix and evaluator were created and executed in the same session. There was no
independent, externally timestamped preregistration, so this result must not be presented as
a confirmatory test.

Each case used five years of observed adjusted OHLCV from YFinance. The first 80% was
available to train/validate/calibrate/qualify the causal model. The last 20% was registered
as an untouched future holdout. Gates require probabilistic skill over training climatology,
positive balanced-accuracy lift and positive median return versus buy-and-hold after a
10-basis-point turnover cost.

Result after right-sizing the over-parameterized neural network:

- 24/24 data cases loaded from the real provider.
- 23/24 failed to beat the validation baseline.
- 1/24 did not converge.
- 0/24 qualified for the untouched holdout.
- Overall verdict: `INVESTMENT_SKILL_NOT_PROVEN`.

The network change was made after the first exploratory run exposed universal convergence
failure. It was selected to reduce model capacity, not from holdout returns, but this remains
same-session model development rather than an independent confirmation. The holdout was not
used for fitting and no failed case was replaced with a neutral prediction.

## Real causal backtest

The live YFinance adapter and penny-momentum path were exercised on SNDL, NOK, PLUG and
OPEN, each with 1,254 observed daily candles (2021-08-23 through 2026-08-20).

The former implementation used the close and volume of bar `t` to generate a signal and
then bought at the same close. It also omitted fees, slippage and benchmarks. The corrected
contract executes at the next observed open, models 5 bps commission plus 10 bps slippage,
and reports cash and equal-weight buy-and-hold.

Official configuration result:

- Trades: 0.
- Strategy return: 0.00% (`NO_TRADE`).
- Equal-weight buy-and-hold: -40.0818%.
- Excess return: +40.0818 percentage points, entirely because the strategy stayed in cash.

This is not evidence of predictive edge. It shows that the official filters generated no
actionable sample in this universe and period.

## Integrity corrections made during the audit

- Generic catalyst/risk/invalidation text can no longer authorize a candidate.
- A liquid fictitious ticker without sourced evidence is `REJECT_ALL`, not confidence 100.
- Social sentiment is no longer relabeled as whale/options/pump evidence.
- Missing social data is `UNKNOWN/NO_DATA`, never `CLEAN`.
- Response quality telemetry now records scorer provenance and the explicit scope
  `response_form_not_investment_accuracy`.
- Live/E2E tests use a diversified configurable matrix; the 100-case overnight suite now
  includes US, Canadian and Brazilian equities, ETFs, crypto, portfolios, macro/no-ticker,
  invalid inputs and edge cases.

## What would constitute evidence later

Collect ex-ante forecasts with immutable timestamps, model IDs and probabilities; freeze an
externally timestamped protocol before collecting outcomes; resolve outcomes only after their
horizon; compare against those frozen baselines over multiple regimes; include costs,
turnover and drawdown; and require a statistically meaningful sample before changing this
verdict.
