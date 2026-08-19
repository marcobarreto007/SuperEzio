# TD Direct Investing Canada — commission-free ETF research

## Scope

SuperEzio maintains a dated snapshot of TD Direct Investing's official commission-free ETF
list in `config/td_direct_commission_free_etfs.json`. The snapshot contains 108 symbols:
83 Canadian-listed and 25 US-listed ETFs, verified on 2026-08-18.

This is a cost filter, not a buy signal. A symbol must still pass independent data provenance,
liquidity, thesis, risk, portfolio, and human-review gates.

## Official conditions

- Source: <https://www.td.com/ca/en/investing/direct-investing/commission-free-etfs>
- Eligible only for simple digital trades through WebBroker, TD app, Advanced Dashboard, or
  TD Active Trader.
- TD Easy Trade is excluded.
- Strategy orders containing an otherwise eligible ETF may still incur commission.
- TD can change the list or fees. Always verify the complete order preview before transmitting.

The local list fails closed after `SUPEREZIO_TD_COMMISSION_LIST_MAX_AGE_DAYS` (default: 7).
Refresh it only from the official TD page and update `verified_at` with evidence.

## API

`GET /trade/td-commission-free` returns the snapshot, count, conditions, and source.

`POST /trade/td-draft` creates only a local research draft. It requires a configured
`SUPEREZIO_API_KEY` and a valid single-use `X-Trading-Token`. It always reports
`ok=false`, `ready_for_execution=false`, and `submitted_to_broker=false` because its quote is
caller-supplied and unverified. It has no TD session, credential, browser automation, or order
transport.

Never enter a TD username, password, account number, cookie, or token in SuperEzio. Open an
official TD platform yourself, confirm symbol/venue/currency/account/quantity/limit and all
fees, then decide manually whether to transmit. Planned stop risk is not a maximum loss:
gaps, slippage, fees, and FX can increase loss.

## Current gate

No real-money go-live is approved. Promotion beyond a draft requires, at minimum, a trusted
server-side quote, Money Gate, portfolio and buying-power checks, durable approval/confirmation,
and independent TD preview verification. Commission-free status never bypasses those gates.
