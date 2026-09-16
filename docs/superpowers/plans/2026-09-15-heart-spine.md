# Heart Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One end-to-end Heart path — NYSE LULD pause on FTFT, same session, gross return — with archive, honest kill, and a one-row ranking panel, all offline.

**Architecture:** Freeze shared fixtures and `PathSpec` first. Each piece writes only its owned files against those contracts. A final parent test (`test_heart_spine.py`) wires the six. No live HTTP. No LightGBM. Missing features on `DailyMove` stay `0.0` with named limitations.

**Tech Stack:** Python 3.12, httpx (mocked), FastAPI TestClient on an isolated router, existing `evaluate_triple_barrier`, `log_return`, SQLite `UniverseRegistry`, JSONL `EventBook` / `RawRecorder`.

**Spec:** `docs/superpowers/specs/2026-09-15-heart-spine-design.md`

## Global Constraints

- Cost zero; no paid APIs; no live network in pytest.
- Missing integration returns a real error — never simulated success.
- Python 3.12, SuperEzio `.venv`: `.\.venv\Scripts\python.exe`
- All spine datetimes timezone-aware; comparisons in `America/New_York`.
- No LLM. No second FastAPI. No MIKE dashboard. No `apps.tmx.com`. No `mlfinpy` CPCV.
- Do not treat existing `src/core/heart/*.py` scaffolding as done; extend public types, do not rename them.
- `RankingWeights.equal()` this cycle; `river.expert` does **not** edit those four floats.
- EDGAR Atom, Perspective, clusters, ArcticDB, full universe: **out of this plan**.
- **Do not git commit unless the operator explicitly asks.** Skip every Commit step.

### File map

| Path | Role | Task |
|---|---|---|
| `tests/fixtures/heart/spine/nyse_halts.csv` | One LULD row | 1 |
| `tests/fixtures/heart/spine/bars.json` | Five as-traded sessions | 1 |
| `tests/fixtures/heart/spine/rss.xml` | One mocked RSS body | 1 |
| `src/core/heart/paths.py` | `PathSpec`, `PathDecision` | 1 |
| `src/core/heart/nyse_halts.py` | CSV → `MarketEvent` | 2 |
| `src/core/heart/event_book.py` | add `ingest_many` | 2 |
| `src/core/heart/listings.py` | one nasdaqtraded line → `ListingRow` | 3 |
| `src/core/heart/moves.py` | bars JSON → `DailyMove` | 3 |
| `src/core/heart/http.py` | UA, gzip, 304, errors | 4 |
| `src/core/heart/identities.py` | GUID or SHA-256 | 4 |
| `src/core/heart/poller.py` | one mocked cycle | 4 |
| `scripts/run_heart_ingest.py` | CLI one cycle | 4 |
| `src/core/heart/attribution.py` | ET tests + `nyse.luld_pause` tier | 5 |
| `src/core/heart/ml/decide.py` | deterministic kill/keep | 6 |
| `src/core/heart/labels.py` | already has widths; reuse | 6 |
| `src/agent_server/heart_endpoints.py` | `GET /api/heart/ranking` | 7 |
| `src/agent_server/main.py` | `include_router` only | 7 |
| `bridge/events.toml` | classify the new route | 7 |
| `tests/test_heart_spine.py` | parent glue | 8 |

Existing tests that already import missing modules (`parse_nyse_halts_csv`, `parse_edgar_atom`, `ingest_many`) are **red today**. Task 2 rewrites `test_ingest_many` to NYSE-only and drops the EDGAR import. Do not implement EDGAR in this plan.

Parallelism: after Task 1, Tasks 2–7 own disjoint files and may run in parallel. Task 8 waits for 2–7.

---

### Task 1: Spine fixtures and PathSpec

**Files:**
- Create: `tests/fixtures/heart/spine/nyse_halts.csv`
- Create: `tests/fixtures/heart/spine/bars.json`
- Create: `tests/fixtures/heart/spine/rss.xml`
- Create: `src/core/heart/paths.py`
- Test: `tests/test_heart_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces: `PathSpec(event_type: str, window: str, axis: str)` with `path_id -> str`; `PathDecision(path_id: str, status: str, weight: float)`; `SPINE_PATH` constant; three fixture files with the exact bytes below

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heart_paths.py
from pathlib import Path

from core.heart.paths import PathDecision, PathSpec, SPINE_PATH

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine"


def test_spine_path_id_is_frozen():
    assert SPINE_PATH == PathSpec(
        event_type="nyse.luld_pause",
        window="same_session",
        axis="gross_return",
    )
    assert SPINE_PATH.path_id == "nyse.luld_pause|same_session|gross_return"


def test_killed_decision_has_zero_weight():
    d = PathDecision(path_id=SPINE_PATH.path_id, status="killed", weight=0.0)
    assert d.status == "killed"
    assert d.weight == 0.0


def test_spine_fixtures_exist_with_required_tokens():
    csv = (FIXTURES / "nyse_halts.csv").read_text(encoding="utf-8")
    assert "FTFT" in csv
    assert "LULD Pause" in csv
    assert "14:44:20" in csv
    bars = (FIXTURES / "bars.json").read_text(encoding="utf-8")
    assert "2026-09-14" in bars
    assert "8.00" in bars or "8.0" in bars
    rss = (FIXTURES / "rss.xml").read_text(encoding="utf-8")
    assert "<rss" in rss.lower() or "<rss" in rss
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_paths.py -q --tb=short`

Expected: FAIL (import `core.heart.paths` missing and/or fixtures missing)

- [ ] **Step 3: Write fixtures and PathSpec**

`tests/fixtures/heart/spine/nyse_halts.csv` (exact):

```csv
Halt Date,Halt Time,Symbol,Name,Exchange,Reason,Resumption Date,Resumption Time
2026-09-14,14:44:20,FTFT,Future FinTech Group Inc.,Nasdaq,LULD Pause,2026-09-14,14:49:20
```

`tests/fixtures/heart/spine/bars.json` (exact):

```json
[
  {"session_date": "2026-09-09", "open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0, "volume": 1000},
  {"session_date": "2026-09-10", "open": 10.2, "high": 10.2, "low": 10.2, "close": 10.2, "volume": 1000},
  {"session_date": "2026-09-11", "open": 10.1, "high": 10.1, "low": 10.1, "close": 10.1, "volume": 1000},
  {"session_date": "2026-09-14", "open": 8.0, "high": 8.0, "low": 8.0, "close": 8.0, "volume": 1000},
  {"session_date": "2026-09-15", "open": 8.2, "high": 8.2, "low": 8.2, "close": 8.2, "volume": 1000}
]
```

`tests/fixtures/heart/spine/rss.xml` (exact):

```xml
<?xml version="1.0"?>
<rss version="2.0"><channel><title>spine</title>
<item><title>FTFT noise</title><guid>spine-guid-1</guid><description>not used in join</description></item>
</channel></rss>
```

`src/core/heart/paths.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

ALLOWED_WINDOWS = frozenset({"same_session"})
ALLOWED_AXES = frozenset(
    {"abnormal_return", "gross_return", "lifetime_score", "surprise"}
)
ALLOWED_STATUS = frozenset({"kept", "killed"})


@dataclass(frozen=True, slots=True)
class PathSpec:
    event_type: str
    window: str
    axis: str

    def __post_init__(self) -> None:
        if self.window not in ALLOWED_WINDOWS:
            raise ValueError(f"unsupported window: {self.window}")
        if self.axis not in ALLOWED_AXES:
            raise ValueError(f"unsupported axis: {self.axis}")

    @property
    def path_id(self) -> str:
        return f"{self.event_type}|{self.window}|{self.axis}"


@dataclass(frozen=True, slots=True)
class PathDecision:
    path_id: str
    status: str
    weight: float

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_STATUS:
            raise ValueError(f"unsupported status: {self.status}")
        if self.weight < 0:
            raise ValueError("weight must be >= 0")
        if self.status == "killed" and self.weight != 0.0:
            raise ValueError("killed paths must have weight 0.0")


SPINE_PATH = PathSpec(
    event_type="nyse.luld_pause",
    window="same_session",
    axis="gross_return",
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_paths.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 2: NYSE halt parser and EventBook.ingest_many

**Files:**
- Create: `src/core/heart/nyse_halts.py`
- Modify: `src/core/heart/event_book.py` (add `ingest_many` after `append`)
- Modify: `tests/test_heart_event_book.py` (drop `edgar_atom` import; NYSE-only ingest)
- Create: `tests/test_heart_nyse_halts.py`

**Interfaces:**
- Consumes: `MarketEvent`, `EventBook.append`, fixture `tests/fixtures/heart/spine/nyse_halts.csv`
- Produces: `parse_nyse_halts_csv(text: str) -> list[MarketEvent]`; `EventBook.ingest_many(events: Sequence[MarketEvent]) -> int` (count newly written)

Parser rules (exact):

- Header row skipped if first cell is `Halt Date`
- Combine halt date + halt time as `datetime` in `ZoneInfo("America/New_York")` (2026-09-14 is EDT, offset `-04:00`)
- `identity = f"nyse-halt:{symbol}:{occurred_at.isoformat()}"` → `nyse-halt:FTFT:2026-09-14T14:44:20-04:00`
- `source = "nyse_halts"`
- `event_type = "nyse.luld_pause"` when reason contains `LULD`; other reasons skipped this cycle
- `timestamp_precision = "second"`
- `symbol` from column; `mic_code = "XNAS"` when Exchange is `Nasdaq` (spine only)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heart_nyse_halts.py
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.heart.nyse_halts import parse_nyse_halts_csv

CSV = (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv").read_text(encoding="utf-8")


def test_luld_row_becomes_spine_market_event():
    events = parse_nyse_halts_csv(CSV)
    assert len(events) == 1
    ev = events[0]
    assert ev.identity == "nyse-halt:FTFT:2026-09-14T14:44:20-04:00"
    assert ev.source == "nyse_halts"
    assert ev.event_type == "nyse.luld_pause"
    assert ev.timestamp_precision == "second"
    assert ev.symbol == "FTFT"
    assert ev.mic_code == "XNAS"
    assert ev.occurred_at == datetime(2026, 9, 14, 14, 44, 20, tzinfo=ZoneInfo("America/New_York"))
```

Replace `test_ingest_many_writes_new_events_skips_duplicates` in `tests/test_heart_event_book.py` with:

```python
def test_ingest_many_writes_new_events_skips_duplicates(book: EventBook):
    from core.heart.nyse_halts import parse_nyse_halts_csv

    nyse_csv = (
        Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "nyse_halts.csv"
    ).read_text(encoding="utf-8")
    batch = parse_nyse_halts_csv(nyse_csv)
    assert book.ingest_many(batch) == 1
    assert len(book.read_all()) == 1
    assert book.ingest_many(batch) == 0
    assert len(book.read_all()) == 1
```

Delete the `parse_edgar_atom` import and any `FIXTURES / "edgar_8k_atom.xml"` / `nyse_halts_sample.csv` references from that file. Keep `test_duplicate_identity_is_a_noop` as-is (it constructs `event_type="LULD"` by hand — a different event, still valid).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_nyse_halts.py tests/test_heart_event_book.py -q --tb=short`

Expected: FAIL on missing `nyse_halts` / `ingest_many`

- [ ] **Step 3: Minimal implementation**

`parse_nyse_halts_csv`: `csv.DictReader` on the text; skip rows whose Reason does not contain `LULD`; build `MarketEvent` as specified.

`EventBook.ingest_many`:

```python
def ingest_many(self, events: Sequence[MarketEvent]) -> int:
    written = 0
    for event in events:
        if self.append(event).written:
            written += 1
    return written
```

Need `from collections.abc import Sequence` if not present.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_nyse_halts.py tests/test_heart_event_book.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 3: Listing + bars → DailyMove

**Files:**
- Create: `src/core/heart/listings.py`
- Create: `src/core/heart/moves.py`
- Create: `tests/fixtures/heart/spine/nasdaqtraded_ftft.txt`
- Test: `tests/test_heart_listings.py`
- Test: `tests/test_heart_moves.py`

**Interfaces:**
- Consumes: `ListingRow`, `listing_exchange_to_mic`, `log_return(current, previous)`, `bars.json`
- Produces: `parse_nasdaqtraded_lines(text: str) -> list[ListingRow]`; `daily_moves_from_bars(*, bars: list[dict], listing: ListingRow, first_seen: str) -> list[DailyMove]`

`DailyMove` for 2026-09-14 (spec §3.2):

- `mic_code="XNAS"`, `symbol="FTFT"`, `first_seen="2020-01-02"`, `session_date="2026-09-14"`
- `gross_ret = log_return(8.0, 10.1)`
- `abnormal_ret=0.0`, `surprise_q=0.0`, `ewma_vol=0.0`

Nasdaqtraded fixture line (pipe-separated, official column order):

```text
Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares
Y|FTFT|Future FinTech Group Inc.|Q|N|N|100|N||FTFT|FTFT|N
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_heart_listings.py
from pathlib import Path

from core.heart.listings import parse_nasdaqtraded_lines


def test_ftft_maps_q_to_xnas():
    text = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "heart"
        / "spine"
        / "nasdaqtraded_ftft.txt"
    ).read_text(encoding="utf-8")
    rows = parse_nasdaqtraded_lines(text)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "FTFT"
    assert row.mic_code == "XNAS"
    assert row.is_test is False
    assert row.source == "nasdaqtraded"
```

```python
# tests/test_heart_moves.py
import json
import math
from pathlib import Path

from core.heart.moves import daily_moves_from_bars
from core.heart.universe import ListingRow
from core.math.risk import log_return

BARS = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "bars.json").read_text(encoding="utf-8")
)


def test_september_14_move_is_log_return_with_honest_zeros():
    listing = ListingRow(
        mic_code="XNAS",
        symbol="FTFT",
        name="Future FinTech Group Inc.",
        exchange="Q",
        source="nasdaqtraded",
    )
    moves = daily_moves_from_bars(bars=BARS, listing=listing, first_seen="2020-01-02")
    target = next(m for m in moves if m["session_date"] == "2026-09-14")
    assert target["mic_code"] == "XNAS"
    assert target["symbol"] == "FTFT"
    assert target["first_seen"] == "2020-01-02"
    assert target["gross_ret"] == log_return(8.0, 10.1)
    assert target["abnormal_ret"] == 0.0
    assert target["surprise_q"] == 0.0
    assert target["ewma_vol"] == 0.0
    assert math.isclose(target["gross_ret"], math.log(8.0 / 10.1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_listings.py tests/test_heart_moves.py -q --tb=short`

Expected: FAIL missing modules

- [ ] **Step 3: Minimal implementation**

`parse_nasdaqtraded_lines`: skip header; skip `Nasdaq Traded != Y`; skip `Test Issue == Y`; `mic_code = listing_exchange_to_mic(Listing Exchange)`.

`daily_moves_from_bars`: sort by `session_date`; first bar has `gross_ret=0.0` (no previous close — do not invent); subsequent bars `log_return(close, prev_close)`. Always zeros for abnormal/surprise/ewma.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_listings.py tests/test_heart_moves.py tests/test_heart_universe.py -q --tb=short`

Expected: PASS (do not break existing universe tests)

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 4: HTTP client and one mocked ingest cycle

**Files:**
- Create: `src/core/heart/http.py`
- Create: `src/core/heart/identities.py`
- Create: `src/core/heart/poller.py`
- Create: `scripts/run_heart_ingest.py`
- Test: `tests/test_heart_http.py`
- Test: `tests/test_heart_identities.py`
- Test: `tests/test_heart_poller.py`
- Test: `tests/test_heart_ingest_cli.py`

**Interfaces:**
- Consumes: env `SUPEREZIO_HEART_USER_AGENT`; `RawRecorder.record`; `feed_by_id`; `httpx.Client`
- Produces: `HeartHttpError`; `HeartResponse(status: int, body: bytes, etag: str | None, last_modified: str | None)`; `build_headers(etag=None, last_modified=None) -> dict[str, str]`; `request(client, url, *, etag=None, last_modified=None) -> HeartResponse`; `item_identity(body: bytes, guid: str | None) -> str`; `poll_once(client, feed, recorder) -> RecordResult`

Rules:

- Missing `SUPEREZIO_HEART_USER_AGENT` → `RuntimeError` matching that name
- Headers: `User-Agent` from env, `Accept-Encoding: gzip`, optional `If-None-Match` / `If-Modified-Since`
- HTTP 304 → `HeartResponse` with `body=b""` (never a fake RSS)
- HTTP 4xx/5xx → `HeartHttpError`
- Identity: `guid` if present else `sha256:{hex}` of body
- `poll_once` uses `recorder.conditional_headers(feed)` then `request` then `recorder.record`
- CLI: `--once --root DIR --feed-id prnewswire`; pytest never writes production `data/heart` (recorder already blocks that)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_heart_http.py
import httpx
import pytest

from core.heart.http import HeartHttpError, build_headers, request


def test_headers_include_contact_ua_and_gzip(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    h = build_headers(etag='"abc"', last_modified="Tue, 15 Sep 2026 16:00:00 GMT")
    assert "marco@example.com" in h["User-Agent"]
    assert h["Accept-Encoding"] == "gzip"
    assert h["If-None-Match"] == '"abc"'
    assert h["If-Modified-Since"] == "Tue, 15 Sep 2026 16:00:00 GMT"


def test_missing_user_agent_is_an_error(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SUPEREZIO_HEART_USER_AGENT"):
        build_headers()


def test_304_returns_empty_body(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": '"abc"'})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    resp = request(client, "https://example.invalid/rss", etag='"abc"')
    assert resp.status == 304
    assert resp.body == b""


def test_500_raises(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"nope")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(HeartHttpError):
        request(client, "https://example.invalid/rss")
```

```python
# tests/test_heart_identities.py
from core.heart.identities import item_identity


def test_guid_wins():
    assert item_identity(b"<rss/>", guid="spine-guid-1") == "spine-guid-1"


def test_hash_when_no_guid():
    ident = item_identity(b"<rss/>", guid=None)
    assert ident.startswith("sha256:")
```

```python
# tests/test_heart_poller.py
from datetime import UTC, datetime
from pathlib import Path

import httpx

from core.heart.feeds import feed_by_id
from core.heart.poller import poll_once
from core.heart.raw_recorder import RawRecorder


def test_one_cycle_appends_jsonl(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    rss = (
        Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "rss.xml"
    ).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=rss, headers={"ETag": '"s"'})

    recorder = RawRecorder(root=tmp_path / "heart")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = poll_once(client, feed_by_id("prnewswire"), recorder)
    assert result.written == 1
    path = recorder.capture_path("prnewswire", result.captured_at)
    assert path.is_file()
    assert "spine-guid-1" in path.read_text(encoding="utf-8") or "FTFT noise" in path.read_text(encoding="utf-8")
```

```python
# tests/test_heart_ingest_cli.py
from pathlib import Path

from scripts.run_heart_ingest import main


def test_cli_once_with_mock_is_callable():
    assert callable(main)
```

Keep `test_heart_ingest_cli.py` thin: importing `main` is enough this cycle. Do not hit the network. If `scripts` is not a package, put `main` in `src/core/heart/poller.py` as `ingest_cli(argv: list[str]) -> int` and have the script call that — **prefer** `core.heart.poller.ingest_cli` so pytest does not fight `scripts/` layout. Then:

```python
from core.heart.poller import ingest_cli

def test_cli_once_with_mock_is_callable():
    assert callable(ingest_cli)
```

`scripts/run_heart_ingest.py` becomes:

```python
from core.heart.poller import ingest_cli
import sys
if __name__ == "__main__":
    raise SystemExit(ingest_cli(sys.argv[1:]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_http.py tests/test_heart_identities.py tests/test_heart_poller.py tests/test_heart_ingest_cli.py tests/test_heart_raw_recorder.py -q --tb=short`

Expected: FAIL missing http/identities/poller; raw_recorder stays green

- [ ] **Step 3: Minimal implementation**

`build_headers` reads env. `request` uses `client.send`/`client.get` with those headers; map status. `poll_once` as specified. Do not parse RSS into `MarketEvent`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_http.py tests/test_heart_identities.py tests/test_heart_poller.py tests/test_heart_ingest_cli.py tests/test_heart_raw_recorder.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 5: Attribution clock in Eastern Time + LULD type

**Files:**
- Modify: `src/core/heart/attribution.py` (`_event_tier` must treat `nyse.luld_pause` as `_TIER_LULD_HALT`)
- Modify: `tests/test_heart_attribution.py` (stamps must be `America/New_York`, not UTC pretending to be 16:00)
- Create: `tests/test_heart_join.py`

**Interfaces:**
- Consumes: `session_impact_date`, `attribute_move`, `DailyMove`, `MarketEvent`, `MIN_AUTO_CONFIDENCE=0.6`
- Produces: same functions; LULD spine event auto-accepted (`confidence >= 0.6`)

Correct clock tests (replace the three existing ones):

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.heart.attribution import session_impact_date

ET = ZoneInfo("America/New_York")


def test_filing_after_regular_close_explains_the_next_session():
    occurred = datetime(2026, 9, 15, 16, 10, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 16)


def test_filing_during_the_session_explains_the_same_day():
    occurred = datetime(2026, 9, 15, 9, 0, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 15)


def test_exact_close_is_next_session():
    occurred = datetime(2026, 9, 15, 16, 0, tzinfo=ET)
    assert session_impact_date(occurred) == date(2026, 9, 16)
```

Join test: LULD 14:44 ET on 2026-09-14 matches the DailyMove of that date; `event_identity` is the spine identity; `confidence >= 0.6`.

```python
# tests/test_heart_join.py
from datetime import datetime
from zoneinfo import ZoneInfo

from core.heart.attribution import attribute_move
from core.heart.event_book import MarketEvent

ET = ZoneInfo("America/New_York")

MOVE = {
    "mic_code": "XNAS",
    "symbol": "FTFT",
    "first_seen": "2020-01-02",
    "session_date": "2026-09-14",
    "abnormal_ret": 0.0,
    "gross_ret": -0.23,
    "surprise_q": 0.0,
    "ewma_vol": 0.0,
}


def test_luld_pause_joins_same_session_and_auto_accepts():
    event = MarketEvent(
        identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
        source="nyse_halts",
        event_type="nyse.luld_pause",
        occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
        timestamp_precision="second",
        symbol="FTFT",
        mic_code="XNAS",
    )
    result = attribute_move(MOVE, [event])
    assert result["event_identity"] == event.identity
    assert result["confidence"] >= 0.6
```

In `_event_tier`, treat `event_type == "nyse.luld_pause"` as LULD tier (keep existing `LULD`/`HALT` tokens).

- [ ] **Step 1: Write/replace failing tests** (join test first; then rewrite attribution clock tests)

- [ ] **Step 2: Run**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_attribution.py tests/test_heart_join.py -q --tb=short`

Expected: clock tests fail or join fails until tier + test stamps are fixed. If current UTC stamps accidentally pass, they are **still wrong** — replace them before considering the task done.

- [ ] **Step 3: Implement matcher + test rewrite**

- [ ] **Step 4: Run to pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_attribution.py tests/test_heart_join.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 6: Deterministic PathDecision (no LightGBM)

**Files:**
- Create: `src/core/heart/ml/__init__.py` (empty or export `decide_path`)
- Create: `src/core/heart/ml/decide.py`
- Test: `tests/test_heart_ml_decide.py`

**Interfaces:**
- Consumes: `barrier_widths`, `vertical_bars_for_sessions`, `label_with_existing_barrier`, `SPINE_PATH`, `PathDecision`, `bars.json`
- Produces: `SPINE_LABEL_SIGMA = 0.05`; `decide_path(bars: list[dict], *, entry_index: int, spec: PathSpec, side: str = "long") -> PathDecision`

Rule (spec §5.1):

```
entry_close = bars[entry_index]["close"]
stop_w, profit_w = barrier_widths(0.05, 1.0, 1.0)
stop = entry_close * (1 - stop_w)
target = entry_close * (1 + profit_w)
touch = label_with_existing_barrier(..., start_index=entry_index, time_horizon_bars=vertical_bars_for_sessions(1))
kept + weight 1.0 iff touch is not None and touch.is_profit
else killed + weight 0.0
```

Entry index of 2026-09-14 in the fixture is `3`. Close `8.0` → stop `7.6`, target `8.4`. That bar and the horizon-1 time exit do not take profit → `killed`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heart_ml_decide.py
import json
from pathlib import Path

from core.heart.ml.decide import decide_path
from core.heart.paths import SPINE_PATH

BARS = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "heart" / "spine" / "bars.json").read_text(encoding="utf-8")
)


def test_spine_path_is_killed_on_the_fixture_crash_bar():
    decision = decide_path(BARS, entry_index=3, spec=SPINE_PATH)
    assert decision.path_id == SPINE_PATH.path_id
    assert decision.status == "killed"
    assert decision.weight == 0.0
```

- [ ] **Step 2: Run to fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_ml_decide.py tests/test_heart_labels.py -q --tb=short`

Expected: FAIL missing `decide_path`; labels tests stay green

- [ ] **Step 3: Implement `decide_path`**

Do not import LightGBM, skfolio, tsfresh, mlflow, or river. Do not change `RankingWeights`.

- [ ] **Step 4: Run to pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_ml_decide.py tests/test_heart_labels.py -q --tb=short`

Expected: PASS. If `evaluate_triple_barrier` returns take-profit on this fixture, **do not shrink sigma**. Document the actual `exit_reason` in the test assertion only after investigating — the spec forbids tightening sigma to force `kept`. The expected status remains `killed` unless the evaluator is proven to hit take-profit at 8.0/8.2 vs 7.6/8.4 (it should not).

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 7: One-row ranking API

**Files:**
- Create: `src/agent_server/heart_endpoints.py`
- Modify: `src/agent_server/main.py` (one `include_router`, no other logic)
- Modify: `bridge/events.toml` (`route_sources` += `src/agent_server/heart_endpoints.py`; classify `GET /api/heart/ranking`)
- Modify: `src/core/heart/ranking.py` only if you must attach `path_id`/`path_status` — prefer attaching in the endpoint after `rank_moves`
- Test: `tests/test_heart_panel_api.py`
- Modify: `tests/test_heart_ranking.py` stays green (`composite_score` unchanged)

**Interfaces:**
- Consumes: `rank_moves`, `RankingWeights.equal()`, `attribute_move`, `decide_path`, `SPINE_PATH`
- Produces: `GET /api/heart/ranking` → JSON `{ "rows": [ ... ], "path_id": str, "path_status": "kept"|"killed"|null }`; `reset_heart_view_for_test()`; in-memory `HeartView` (`moves`, `events`, `bars`)

Empty `moves` → HTTP 200, `rows: []`, `path_status: null` (real empty state, not 204).

Killed path → HTTP 200, one FTFT row, `path_status: "killed"`.

Do **not** import `agent_server.main` in the unit test. Mirror `tests/test_control_endpoints.py`: mount `heart_endpoints.router` on a bare `FastAPI()`.

`events.toml` entry (class `internal`, snapshot false, MIKE does not poll this):

```toml
"GET /api/heart/ranking" = { class = "internal", snapshot = false, mutable = false, bridge_calls = false, emits = [], source = "src/agent_server/heart_endpoints.py:LINE", note = "Heart spine ranking; not a bridge poll surface" }
```

Replace `LINE` with the real decorator line after writing the file. Add the file to `meta.route_sources`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_heart_panel_api.py
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server import heart_endpoints as heart
from core.heart.event_book import MarketEvent

ET = ZoneInfo("America/New_York")


def test_killed_spine_row_is_present():
    heart.reset_heart_view_for_test()
    heart.VIEW.moves = [
        {
            "mic_code": "XNAS",
            "symbol": "FTFT",
            "first_seen": "2020-01-02",
            "session_date": "2026-09-14",
            "abnormal_ret": 0.0,
            "gross_ret": -0.23,
            "surprise_q": 0.0,
            "ewma_vol": 0.0,
        }
    ]
    heart.VIEW.events = [
        MarketEvent(
            identity="nyse-halt:FTFT:2026-09-14T14:44:20-04:00",
            source="nyse_halts",
            event_type="nyse.luld_pause",
            occurred_at=datetime(2026, 9, 14, 14, 44, 20, tzinfo=ET),
            timestamp_precision="second",
            symbol="FTFT",
            mic_code="XNAS",
        )
    ]
    heart.VIEW.bars = [
        {"session_date": "2026-09-09", "close": 10.0},
        {"session_date": "2026-09-10", "close": 10.2},
        {"session_date": "2026-09-11", "close": 10.1},
        {"session_date": "2026-09-14", "close": 8.0},
        {"session_date": "2026-09-15", "close": 8.2},
    ]
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    client = TestClient(app)
    response = client.get("/api/heart/ranking")
    assert response.status_code == 200
    body = response.json()
    assert body["path_status"] == "killed"
    assert body["path_id"] == "nyse.luld_pause|same_session|gross_return"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["symbol"] == "FTFT"


def test_empty_view_is_empty_rows_not_error():
    heart.reset_heart_view_for_test()
    app = FastAPI()
    app.router.routes.extend(heart.router.routes)
    response = TestClient(app).get("/api/heart/ranking")
    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert response.json()["path_status"] is None
```

For `decide_path`, bars need open/high/low or close-only is enough (`_bar_fields` falls back to close). Close-only dicts are fine.

- [ ] **Step 2: Run to fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_panel_api.py tests/test_heart_ranking.py -q --tb=short`

Expected: FAIL missing router

- [ ] **Step 3: Implement endpoint, mount, classify**

`include_router` in `main.py` only. Do not copy JWT logic. Isolated tests never hit JWT.

- [ ] **Step 4: Run to pass including the events.toml gate**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_panel_api.py tests/test_heart_ranking.py tests/test_control_endpoints.py::test_events_toml_classifies_every_route_of_the_server tests/test_control_endpoints.py::test_events_toml_entries_are_well_formed -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

Skip unless the operator asks.

---

### Task 8: Parent spine test (do not start until 2–7 are green)

**Files:**
- Create: `tests/test_heart_spine.py`

**Interfaces:**
- Consumes: fixtures from Task 1; `parse_nyse_halts_csv`; `daily_moves_from_bars`; `parse_nasdaqtraded_lines`; `attribute_move`; `poll_once` + `RawRecorder`; `decide_path`; ranking endpoint helpers
- Produces: one test proving spec §10 without network

- [ ] **Step 1: Write the failing test** (it should fail only if a prior piece drifted)

```python
# tests/test_heart_spine.py
"""Spec aceite: um LULD FTFT, arquivo P0, junção, ranking killed visível."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from core.heart.attribution import attribute_move
from core.heart.feeds import feed_by_id
from core.heart.listings import parse_nasdaqtraded_lines
from core.heart.ml.decide import decide_path
from core.heart.moves import daily_moves_from_bars
from core.heart.nyse_halts import parse_nyse_halts_csv
from core.heart.paths import SPINE_PATH
from core.heart.poller import poll_once
from core.heart.raw_recorder import RawRecorder
from core.heart.ranking import RankingWeights, rank_moves

ROOT = Path(__file__).resolve().parent / "fixtures" / "heart" / "spine"


@pytest.fixture
def ua(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")


def test_spine_archive_join_kill_and_row(tmp_path, ua):
    rss = (ROOT / "rss.xml").read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=rss, headers={"ETag": '"s"'})

    rec = RawRecorder(root=tmp_path / "heart")
    result = poll_once(httpx.Client(transport=httpx.MockTransport(handler)), feed_by_id("prnewswire"), rec)
    assert result.written == 1

    events = parse_nyse_halts_csv((ROOT / "nyse_halts.csv").read_text(encoding="utf-8"))
    assert events[0].event_type == "nyse.luld_pause"

    listing = parse_nasdaqtraded_lines(
        (ROOT / "nasdaqtraded_ftft.txt").read_text(encoding="utf-8")
    )[0]
    bars = json.loads((ROOT / "bars.json").read_text(encoding="utf-8"))
    moves = daily_moves_from_bars(bars=bars, listing=listing, first_seen="2020-01-02")
    day = next(m for m in moves if m["session_date"] == "2026-09-14")
    att = attribute_move(day, events)
    assert att["event_identity"] == events[0].identity
    assert att["confidence"] >= 0.6

    decision = decide_path(bars, entry_index=3, spec=SPINE_PATH)
    assert decision.status == "killed"

    ranked = rank_moves([day], RankingWeights.equal(), attributions={att["move_key"]: att})
    assert ranked[0]["symbol"] == "FTFT"
    ranked[0]["path_status"] = decision.status
    ranked[0]["path_id"] = decision.path_id
    assert ranked[0]["path_status"] == "killed"
```

This test does not require the HTTP app (Task 7 already covers `path_status` on the wire). It is the spec §10 glue for P0–P3+P5.

- [ ] **Step 2: Run**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_spine.py tests/test_heart_*.py -q --tb=short`

Expected: PASS all Heart tests. If anything fails, fix the owning piece — do not weaken `test_heart_spine.py`.

- [ ] **Step 3: Full regression gate (espinha fechada)**

Run: `.\.venv\Scripts\python.exe -m pytest -q --tb=line`

Expected: 2890 baseline plus new heart tests, 0 new reds. Only at this step, not after every piece.

- [ ] **Step 4: Commit**

Skip unless the operator asks.

---

## Self-review (plan vs spec)

| Spec section | Task |
|---|---|
| §2 path / FTFT / identity | 1, 2 |
| §3.1 MarketEvent | 2 |
| §3.2 DailyMove zeros | 3 |
| §3.3 RankingWeights.equal | 7, 8 |
| §3.4 PathSpec / PathDecision | 1, 6 |
| §3.5 ET clock | 5 |
| §3.6 identity (mic, symbol, first_seen) | 3 |
| §3.7 P0 recorder, not in join | 4, 8 |
| §4 bars | 1, 3 |
| §5.1 killed on crash bar | 6, 7, 8 |
| §6 errors / 304 / UA | 4 |
| §7 ownership / no EDGAR / no Perspective | 2 (EDGAR dropped), 7 (no browser) |
| §8 out of scope | no tasks for those items |
| §10 aceite | 8 + 7 |

Placeholders: none. `ingest_cli` vs `scripts` import is resolved (CLI lives in `poller.py`).
