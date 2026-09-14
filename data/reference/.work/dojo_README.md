---
license: apache-2.0
---

> **Languages:** [简体中文](README_ZH.md) · [English](README.md)

# dojo_stock_kline — Stock Daily Bars

## Overview

Daily OHLCV history for US, CN, and HK equities, including cumulative adjustment factors and dividend/split flags.

## Files

| File | Description |
|------|-------------|
| `data.parquet` | Market-wide daily bars |

## Key Fields

| Field | Description |
|-------|-------------|
| `symbol` | Join key |
| `kline_t` | Bar interval; snapshots use `"1D"` for daily bars |
| `bar_time` | Bar timestamp (trade date) |
| `open` / `high` / `low` / `close` | OHLC |
| `vol` / `amount` | Volume / turnover |
| `change_p` | Percent change |
| `adj_factor_cum` | Cumulative adjustment factor |
| `dividends` / `splits` | Dividend / split flags |

## Scale (reference)

~**4.86M** rows (symbol × trade dates).

## Data Notes

- Filter by `symbol` when reading; parquet supports predicate pushdown on this column.
- Rows are ordered by `bar_time` per symbol in typical exports.

## Related Datasets

- [dojo_stock_info](https://huggingface.co/datasets/AlphaDojo/dojo_stock_info) / [dojo_quote](https://huggingface.co/datasets/AlphaDojo/dojo_quote) — symbol mapping
- [dojo_sector_precomputed](https://huggingface.co/datasets/AlphaDojo/dojo_sector_precomputed) — sector indices derived from this data
- [dojo_fin_indicators](https://huggingface.co/datasets/AlphaDojo/dojo_fin_indicators) — EPS and fundamentals for valuation overlays
