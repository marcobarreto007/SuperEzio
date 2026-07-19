# TWS limit-order preset guidance

## Problem

An Interactive Brokers paper account can apply TWS presets that cancel or alter limit orders immediately.

## Current code contract

- The raw `_ibkr_order.py` command is retired and never contacts IBKR.
- Prepared orders pass through `InteractiveBrokersAdapter` and its isolated worker.
- Limit orders use explicit `GTC` time-in-force in the worker.
- Market orders remain blocked by default.
- Orders require F51 approval, matching ticker evidence, weighted consensus, adaptive sizing, and a healthy journal before the adapter accepts them.

## TWS configuration

1. Open the paper-trading TWS account.
2. Open **Configuration → Order Presets**.
3. Inspect the stock preset for automatic cancellation or conflicting time-in-force rules.
4. Disable only the conflicting preset.
5. Submit through the SuperEzio prepared pipeline and verify the order in the TWS order book.

Do not use the retired raw CLI or switch to market orders as a workaround.
