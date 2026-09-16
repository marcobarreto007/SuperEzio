# Heart P1 Price Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Point-in-time identity for ~18 400 TD-tradable symbols plus decades of **as-traded** daily OHLCV and reconciled corporate actions, so the loss ranking is not a split table.

**Architecture:** SQLite `symbol_history` keyed by `(mic_code, symbol, first_seen)`. Bars live in ArcticDB (LMDB local) per identity; DuckDB reads Parquet exports for cross-sectional queries. Yahoo `chart?events=split|div&period1=0` is the CA spine; archive close always wins the jump test. Nightly job writes features beside bars, not through MathHub or DataHub.

**Tech Stack:** Python 3.12, sqlite3, arcticdb, duckdb, pyarrow, pandas, statsmodels, arch, exchange-calendars, pandas-market-calendars, httpx/yfinance only as a thin Yahoo chart client outside DataHub.

**Spec:** `docs/superpowers/specs/2026-09-15-modulo-coracao-roadmap.md` §3–4, §5 (do not reuse MathHub/DataHub/historical_cache), §6 Peça 1, §7 manifests.

## Global Constraints

- Cost zero.
- As-traded storage; never treat Yahoo `adjclose/close` as a split detector.
- Identity is never ticker-alone (FB/BBBY recycle).
- Failed download ≠ delisting.
- Yahoo 404 freezes the series; do not merge into a new homonym.
- OLS market model uses `cov_type="HAC"`.
- Calendar must use `early_closes()`.
- New deps are those already chosen in the roadmap (ask before adding anything else).
- Torch in this venv must stay ≤2.7 if present (1080 Ti sm_61).
- Existing `universe.py` / `corporate_actions.py` stubs may be extended.

---

## File map

| Path | Role |
|---|---|
| `src/core/heart/universe.py` | Identity registry (exists) |
| `src/core/heart/listings.py` | Parse nasdaqtraded.txt, TSX JSON instruments, CSE Twelve Data |
| `src/core/heart/corporate_actions.py` | Jump classifier (exists) |
| `src/core/heart/yahoo_chart.py` | Fetch unadjusted intent + events block |
| `src/core/heart/bar_store.py` | ArcticDB write/read by identity |
| `src/core/heart/feature_nightly.py` | log-return, beta, AR, EWMA, volume, gap, surprise |
| `src/core/heart/freeze_manifest.py` | SHA256 + limitations list |
| `scripts/run_heart_universe.py` | Daily listing ingest |
| `scripts/run_heart_bars.py` | Bar + CA backfill/update |
| `tests/test_heart_listings.py` | Parsers on fixtures |
| `tests/test_heart_universe.py` | Already covers recycle/failed snapshot |
| `tests/test_heart_corporate_actions.py` | Already covers jump rules |
| `tests/test_heart_bar_store.py` | Fake/in-memory store if Arctic unavailable in unit tests |
| `tests/test_heart_feature_nightly.py` | Synthetic bars |
| `tests/test_heart_freeze_manifest.py` | Hash + limitations |

---

### Task 1: Listing parsers (fixtures only)

**Files:** Create `src/core/heart/listings.py`, `tests/test_heart_listings.py`, fixtures under `tests/fixtures/heart/`

**Interfaces:**
- Produces: `parse_nasdaqtraded(text) -> list[ListingRow]` mapping Q/N/P/A/Z/V → MIC, drop `Test Issue == Y`
- Produces: `parse_tsx_directory(payload: dict, mic: str) -> list[ListingRow]` flattening `instruments`
- Produces: `parse_twelve_cse(payload: dict) -> list[ListingRow]` mic `XCNQ`

```python
def test_nasdaqtraded_keeps_cboe_bzx_and_drops_test():
    text = "Nasdaq Traded|Symbol|...|Listing Exchange|...|Test Issue\nY|AAA|...|Z|...|N\nY|ZZZ|...|Q|...|Y\n"
    rows = parse_nasdaqtraded(text)
    assert [r.mic_code for r in rows] == ["BATS"]
```

- [ ] TDD; commit `feat(heart): listing parsers for US/TSX/CSE`

---

### Task 2: Wire parsers into UniverseRegistry daily ingest

**Files:** Modify `universe.py`; create `scripts/run_heart_universe.py`; test `tests/test_heart_universe_ingest.py`

**Interfaces:**
- Consumes: `ListingRow`, `UniverseRegistry.ingest_snapshot(..., snapshot_ok=bool)`
- Produces: CLI `--source nasdaqtraded --file path --as-of 2026-09-15` with `--snapshot-failed` flag

- [ ] Unit test: snapshot_failed empty file does not delist (already in universe tests — add CLI mapping)
- [ ] Commit `feat(heart): daily universe ingest CLI`

---

### Task 3: Yahoo events client (mocked HTTP)

**Files:** Create `src/core/heart/yahoo_chart.py`, `tests/test_heart_yahoo_chart.py`

**Interfaces:**
- Produces: `YahooChart(events_splits, events_divs, closes_as_returned, status)`
- `fetch_chart(symbol) -> YahooChart`; status 404 → `missing=True` (maps to `freeze_on_yahoo_missing`)

```python
def test_404_is_missing_not_empty_history():
    chart = parse_chart_response(status=404, payload=b"")
    assert chart.missing is True
```

Document: Yahoo `close` is split-adjusted; we still store **our** bars as-traded from a source that offers raw close (Massive grouped-daily / TMX — client in a later task). This task only persists the **event table**.

- [ ] Commit `feat(heart): Yahoo chart events client`

---

### Task 4: Bar store interface (unit-testable without Arctic)

**Files:** Create `src/core/heart/bar_store.py`, `tests/test_heart_bar_store.py`

**Interfaces:**
- Produces: `BarStore.append(identity, frame)`; `BarStore.read(identity) -> DataFrame` with columns date, open, high, low, close, volume, as_traded=True
- Default impl: parquet under `data/heart/bars/` for tests; ArcticDB adapter behind `SUPEREZIO_HEART_BAR_BACKEND=arctic|parquet`

```python
def test_append_is_as_traded_flagged(tmp_path):
    store = BarStore(tmp_path, backend="parquet")
    store.append(("XNAS", "AAPL", date(1980, 12, 12)), frame)
    out = store.read(("XNAS", "AAPL", date(1980, 12, 12)))
    assert out.attrs["as_traded"] is True
```

- [ ] Commit `feat(heart): bar store with parquet backend for tests`

---

### Task 5: Reconcile splits against as-traded bars

**Files:** Modify `corporate_actions.py`; test extend `tests/test_heart_corporate_actions.py`

**Interfaces:**
- Consumes: `classify_split_day`, `BarStore`, Yahoo events
- Produces: `reconcile_symbol(bars, events) -> list[SplitDecision]`

Acceptance helper:

```python
def test_top_drops_exclude_confirmed_splits():
    # synthetic 10:1 then a real -8% day
    ranking = largest_drops(reconciled)
    assert ranking[0].kind != "confirmed_split"
```

- [ ] Commit `feat(heart): split reconciliation vs as-traded archive`

---

### Task 6: Nightly features

**Files:** Create `src/core/heart/feature_nightly.py`, `tests/test_heart_feature_nightly.py`

**Interfaces:**
- Consumes: as-traded bars, market index bars, `core.math.risk.log_return`, `core.math.utils.zscore` (call the canonical functions — do not copy)
- Produces: `compute_daily_features(asset: DataFrame, market: DataFrame) -> DataFrame` with columns `log_ret`, `beta`, `abnormal_ret`, `ewma_vol`, `volume_rel`, `gap_vs_range`, `surprise_q`

```python
def test_beta_uses_hac_ols(monkeypatch):
    captured = {}
    def fake_ols(*a, **k):
        captured.update(k)
        ...
    monkeypatch.setattr("statsmodels.api.OLS", fake_ols)
    compute_daily_features(...)
    assert captured.get("cov_type") == "HAC" or captured["fit_kwargs"]["cov_type"] == "HAC"
```

- [ ] Commit `feat(heart): nightly abnormal-return features`

---

### Task 7: Freeze manifest

**Files:** Create `src/core/heart/freeze_manifest.py`, `tests/test_heart_freeze_manifest.py`

**Interfaces:**
- Produces: JSON with `input_sha256`, `sources[].source_sha256`, `adjustment: "as_traded"`, `limitations: [...]`

Copy the honesty of `scripts/prepare_event_ml_input.py` limitations; **do not** use `auto_adjust=True`.

- [ ] Commit `feat(heart): freeze manifest for as-traded snapshots`

---

## Spec coverage

| Requirement | Task |
|---|---|
| (mic, symbol, first_seen) | existing universe + 2 |
| Cboe BZX via nasdaqtraded Z | 1 |
| Failed file ≠ delist | existing + 2 |
| As-traded + Arctic/Parquet | 4 |
| Yahoo events, not adj/close | 3, 5 |
| 404 freeze | 3 |
| Nightly AR / EWMA / surprise | 6 |
| Manifest hashes | 7 |
| Top drops not splits | 5 |

## Impossible for free (document in limitations)

- Canadian delistings at daily grain; TSXV dead names; official CA tape.

**Do not claim Peça 1 closed until a fixture universe produces a drop ranking with zero confirmed splits in the top N.**
