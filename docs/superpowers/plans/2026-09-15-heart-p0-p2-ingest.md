# Heart P0+P2 Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop losing irrecoverable press wires (P0) and turn dated market events — NYSE LULD halts, SEC Atom, classified wires — into an append-only event book (P2).

**Architecture:** A dedicated HTTP client (not DataHub) polls sweep-only feeds with conditional headers. P0 writes raw bodies + item identities to date-partitioned JSONL. P2 re-reads those dumps plus recoverable clocks (NYSE halt CSV, EDGAR Atom) into `EventBook` rows with `occurred_at` and `timestamp_precision`. Hot path is append-only; never `_rewrite`.

**Tech Stack:** Python 3.12, httpx, stdlib XML, existing JSONL lock pattern from `paper_journal._journal_file_lock`.

**Spec:** `docs/superpowers/specs/2026-09-15-modulo-coracao-roadmap.md` §6 Peça 0, §6 Peça 2, §7.

## Global Constraints

- Cost zero; no paid APIs.
- Missing integration returns a real error — never simulated success.
- Python 3.12, SuperEzio `.venv`.
- User-Agent must include a real contact email (`SUPEREZIO_HEART_USER_AGENT`).
- `Accept-Encoding: gzip`; send `If-None-Match` / `If-Modified-Since` when stored.
- SEC ≤ 8 req/s; Nasdaq trade-halts RSS ≤ 1/min; GlobeNewswire ≤ 1/min; tsx.com crawl-delay 15s.
- Never automate `apps.tmx.com` or `tsx.com/resource/`.
- Unit tests mock HTTP; no live network in pytest.
- Regression gate: `.\.venv\Scripts\python.exe -m pytest tests/test_heart_*.py -q` plus full suite at piece close.
- Existing `src/core/heart/{feeds,raw_recorder,event_book}.py` is scaffolding — extend or replace; do not treat it as done.

---

## File map

| Path | Role |
|---|---|
| `src/core/heart/http.py` | Shared headers, 304, gzip, error mapping |
| `src/core/heart/feeds.py` | Catalog of non-recoverable + recoverable clocks |
| `src/core/heart/identities.py` | GUID / Atom id / content-hash fallback |
| `src/core/heart/raw_recorder.py` | Raw JSONL dump + identity index |
| `src/core/heart/poller.py` | One poll cycle; persist ETag state |
| `src/core/heart/nyse_halts.py` | Parse NYSE halt CSV → MarketEvent |
| `src/core/heart/edgar_atom.py` | Parse SEC getcurrent Atom → MarketEvent |
| `src/core/heart/event_book.py` | Append-only normalized ledger |
| `scripts/run_heart_ingest.py` | 24h / cron entry |
| `tests/test_heart_http.py` | Header + 304 + error contracts |
| `tests/test_heart_identities.py` | GUID / hash |
| `tests/test_heart_raw_recorder.py` | Extend existing |
| `tests/test_heart_poller.py` | Mocked cycle |
| `tests/test_heart_nyse_halts.py` | CSV fixture |
| `tests/test_heart_edgar_atom.py` | Atom fixture |
| `tests/test_heart_event_book.py` | Extend existing |

---

### Task 1: HTTP client contract

**Files:**
- Create: `src/core/heart/http.py`
- Test: `tests/test_heart_http.py`

**Interfaces:**
- Consumes: env `SUPEREZIO_HEART_USER_AGENT`
- Produces: `HeartHttpError`, `HeartResponse(status, body, etag, last_modified)`, `build_headers(etag=None, last_modified=None) -> dict`, `request(client, url, *, etag=None, last_modified=None) -> HeartResponse`

- [ ] **Step 1: Write the failing test**

```python
def test_headers_include_contact_ua_and_gzip(monkeypatch):
    monkeypatch.setenv("SUPEREZIO_HEART_USER_AGENT", "SuperEzioHeart/1.0 (marco@example.com)")
    from core.heart.http import build_headers
    h = build_headers(etag='"abc"', last_modified="Tue, 15 Sep 2026 16:00:00 GMT")
    assert "marco@example.com" in h["User-Agent"]
    assert h["Accept-Encoding"] == "gzip"
    assert h["If-None-Match"] == '"abc"'
    assert h["If-Modified-Since"] == "Tue, 15 Sep 2026 16:00:00 GMT"


def test_missing_user_agent_is_an_error(monkeypatch):
    monkeypatch.delenv("SUPEREZIO_HEART_USER_AGENT", raising=False)
    from core.heart.http import build_headers
    import pytest
    with pytest.raises(RuntimeError, match="SUPEREZIO_HEART_USER_AGENT"):
        build_headers()


def test_http_error_is_not_success():
    from core.heart.http import HeartHttpError
    err = HeartHttpError(status=403, url="https://www.sec.gov/x", detail="forbidden")
    assert err.status == 403
    assert "success" not in str(err).lower()
```

- [ ] **Step 2:** `.\.venv\Scripts\python.exe -m pytest tests/test_heart_http.py -q` → FAIL import
- [ ] **Step 3:** Implement `build_headers` / `HeartHttpError` / `request` wrapping httpx; 304 returns `HeartResponse(status=304, body=b"")`; 4xx/5xx raise `HeartHttpError` with status (never a fake payload)
- [ ] **Step 4:** tests PASS
- [ ] **Step 5:** Commit `feat(heart): HTTP headers and real error mapping`

---

### Task 2: Item identity (GUID then content hash)

**Files:**
- Create: `src/core/heart/identities.py`
- Test: `tests/test_heart_identities.py`

**Interfaces:**
- Consumes: raw XML/RSS/Atom bytes
- Produces: `iter_item_identities(body: bytes) -> list[str]` — RSS `<guid>`, else `<link>`, else Atom `<id>`, else `sha256:` + hash of item XML

- [ ] **Step 1: Failing tests** with a 2-item RSS (one guid, one without) and one Atom entry
- [ ] **Step 2:** pytest FAIL
- [ ] **Step 3:** stdlib `xml.etree` parser; never raise on one bad item — skip that item and continue
- [ ] **Step 4:** PASS
- [ ] **Step 5:** Commit `feat(heart): GUID identity with content-hash fallback`

---

### Task 3: Extend raw recorder for identities + 304 stats

**Files:**
- Modify: `src/core/heart/raw_recorder.py`
- Modify: `src/core/heart/feeds.py` — full catalog from spec (PRN, CNW, 12 Business Wire slots as config keys, Newsfile global+4 industry, GNW, nasdaq rssoutbound, reddit placeholder URL)
- Test: extend `tests/test_heart_raw_recorder.py`

**Interfaces:**
- Consumes: `HeartResponse`, `iter_item_identities`
- Produces: `RawRecorder.record(...)` already exists; add `record_identities(feed_id, identities) -> skipped_count`; `PollStats(not_modified: int, written: int, duplicate_guids: int)`

- [ ] Tests: duplicate GUID across two 200 bodies with different wrapping XML still skipped; 304 increments `not_modified`; catalog contains `prnewswire`, `cnw`, `businesswire_ma`, `newsfile`, `globenewswire`, `nasdaq_rssoutbound`
- [ ] Reddit feed is listed but poller must no-op with `HeartHttpError` if OAuth token env missing (no silent empty success)
- [ ] Commit `feat(heart): identity-aware raw dump and feed catalog`

---

### Task 4: One mocked poll cycle

**Files:**
- Create: `src/core/heart/poller.py`
- Test: `tests/test_heart_poller.py`

**Interfaces:**
- Consumes: `build_headers`, `request`, `RawRecorder`, `FeedSpec`
- Produces: `async def poll_once(feeds, recorder, client) -> PollStats`

```python
def test_304_writes_nothing(monkeypatch, tmp_path):
    # fake client returns 304 for prnewswire
    ...
    assert stats.not_modified == 1
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_403_does_not_look_like_success():
    with pytest.raises(HeartHttpError):
        poll_once(...)
```

- [ ] Implement sequential poll (no burst). Persist ETag after 200.
- [ ] Commit `feat(heart): poll_once with conditional GETs`

---

### Task 5: NYSE halt CSV → events

**Files:**
- Create: `src/core/heart/nyse_halts.py`
- Test: `tests/test_heart_nyse_halts.py` with fixture copied from the measured LULD line:
  `2026-09-14,14:44:20,FTFT,...,Nasdaq,LULD Pause,2026-09-14,14:49:20`

**Interfaces:**
- Produces: `parse_nyse_halts_csv(text: str) -> list[MarketEvent]` with `timestamp_precision="second"`, `event_type="LULD"` or halt reason, `identity="nyse-halt:{symbol}:{iso}"`

- [ ] TDD then commit `feat(heart): NYSE halt CSV parser`

---

### Task 6: SEC Atom → events

**Files:**
- Create: `src/core/heart/edgar_atom.py`
- Test: `tests/test_heart_edgar_atom.py` with a minimal Atom `<entry>` for type=8-K

**Interfaces:**
- Produces: `parse_edgar_atom(body: bytes, form: str) -> list[MarketEvent]`
- User-Agent contract tested via `build_headers` (browser UA must not be used)

- [ ] Commit `feat(heart): EDGAR getcurrent Atom parser`

---

### Task 7: Event book ingest from parsers

**Files:**
- Modify: `src/core/heart/event_book.py`
- Test: `tests/test_heart_event_book.py`

**Interfaces:**
- Consumes: `MarketEvent` from Tasks 5–6
- Produces: `EventBook.append` (exists); add `ingest_many(events) -> int written`

- [ ] Duplicate identity no-op; corrupt line quarantine already tested
- [ ] Commit `feat(heart): event book ingest_many`

---

### Task 8: CLI for 24h run (no network in tests)

**Files:**
- Create: `scripts/run_heart_ingest.py`
- Test: `tests/test_heart_ingest_cli.py` — argparse dry-run prints feed ids, refuses to start without UA env

- [ ] Commit `feat(heart): ingest CLI dry-run`

---

## Spec coverage

| Spec requirement | Task |
|---|---|
| P0 dump irrecoverable wires | 3, 4 |
| ETag / Last-Modified / gzip / UA | 1, 4 |
| GUID dedup + content hash | 2, 3 |
| 24h process | 8 (ops); acceptance still needs a live overnight after merge |
| NYSE LULD clock | 5 |
| SEC Atom 8-K/4/13D/25 | 6 (start with 8-K; add form loop in same module) |
| Event book precision | 7 |
| No apps.tmx /resource scrape | catalog comment + no URLs in feeds.py |
| Reddit OAuth missing = error | 3 |

## Uncertainties

- Business Wire subject codes are opaque base64; catalog uses stable keys, URLs filled from `config/heart_feeds.yaml` once harvested from their feed builder.
- Reddit OAuth app not registered yet; poller must fail closed.
- P2 “8-K in book in <2 min” is an integration/live acceptance, not a unit test.

**Do not start P3 until P0 has written real files on disk for one market session and P2 can parse NYSE+EDGAR fixtures.**
