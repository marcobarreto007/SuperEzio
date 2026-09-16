# Heart P3+P4 Cause and Ranking Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Join abnormal price moves to dated events with confidence and show a SuperEzio tab that ranks lifetime gains/losses with the evidence attached.

**Architecture:** P3 is a DuckDB/SQL temporal join plus a precedence policy and a clustered significance test. P4 is a new page on the **existing** FastAPI app (no second server) serving Perspective + lightweight-charts. Ranking weights are an input interface; learning them is P5.

**Tech Stack:** Python 3.12, FastAPI, DuckDB, scipy/statsmodels, Perspective, lightweight-charts, Playwright tests.

**Spec:** `docs/superpowers/specs/2026-09-15-modulo-coracao-roadmap.md` §6 Peça 3–4, §5 extend frontend, §9 P3 after P1+P2.

## Global Constraints

- Horizon is **sessions**, not minutes.
- No LLM.
- Cross-sectional correlation must be treated (one FDA ≠ 300 independent biotechs).
- Human correction is optional, one click, logged as human.
- Declare P3 accuracy threshold **before** measuring.
- Same FastAPI process as SuperEzio (`src/agent_server/main.py` static mount).
- Do not compute features inside MathHub.

## Frozen contracts consumed (even before P1/P2 finish)

```python
# P1 feature row
class DailyMove(TypedDict):
    mic_code: str
    symbol: str
    first_seen: str  # ISO date
    session_date: str
    abnormal_ret: float
    gross_ret: float
    surprise_q: float
    ewma_vol: float

# P2 event row — MarketEvent.to_row()
# identity, source, event_type, occurred_at, timestamp_precision, symbol, mic_code
```

P3 produces:

```python
class Attribution(TypedDict):
    move_key: str
    event_identity: str | None
    confidence: float
    evidence: dict
    cluster_id: str | None
    human_override: str | None
```

---

## File map

| Path | Role |
|---|---|
| `src/core/heart/attribution.py` | session_impact_date (exists) + join + precedence |
| `src/core/heart/clusters.py` | same-day same-event clustering |
| `src/core/heart/ranking.py` | composite_score (exists) + rank_moves |
| `src/core/heart/corrections.py` | human override JSONL |
| `src/agent_server/heart_endpoints.py` | `/api/heart/ranking`, `/api/heart/moves/{key}` |
| `frontend/heart.html` + `frontend/js/heart_panel.js` | second tab/page |
| `tests/test_heart_attribution.py` | extend |
| `tests/test_heart_join.py` | join cases |
| `tests/test_heart_clusters.py` | 300→1 |
| `tests/test_heart_panel_api.py` | FastAPI TestClient |
| `tests/test_heart_panel_browser.py` | Playwright, follow `test_td_research_browser.py` |

---

### Task 1: Asymmetric window (already stubbed — lock tests)

**Files:** `attribution.py`, `tests/test_heart_attribution.py`

Keep existing tests (16:10 → next day, 09:00 → same day, exact 16:00 → next). Add timezone note: inputs are UTC; session close 16:00 **America/New_York** must be converted.

```python
def test_et_1600_not_utc_1600():
    # 20:00 UTC in September is 16:00 ET
    occurred = datetime(2026, 9, 15, 20, 0, tzinfo=UTC)
    assert session_impact_date(occurred, session_tz="America/New_York") == date(2026, 9, 16)
```

- [ ] Fix stub to use America/New_York, not naive UTC hour==16
- [ ] Commit `fix(heart): session impact date in US/Eastern`

---

### Task 2: Temporal join + precedence

**Files:** Create join helpers in `attribution.py`; `tests/test_heart_join.py`

**Interfaces:**
- Produces: `attribute_move(move: DailyMove, events: Sequence[MarketEvent]) -> Attribution`

Precedence (highest first): LULD/halt same second → 8-K/Form 4 in window → classified Business Wire → RSS headline with structured ticker → unexplained.

```python
def test_post_close_8k_beats_morning_rss():
    move = {... session_date: "2026-09-16" ...}
    events = [rss_morning_sep16, form8k_sep15_1610]
    att = attribute_move(move, events)
    assert att["event_identity"].startswith("sec:8-k")
```

Threshold declared in code constant `MIN_AUTO_CONFIDENCE = 0.6` **before** any golden-set measurement.

- [ ] Commit `feat(heart): event-move join with precedence`

---

### Task 3: Cross-section cluster

**Files:** `src/core/heart/clusters.py`, `tests/test_heart_clusters.py`

**Interfaces:**
- Produces: `cluster_same_event(attributions) -> dict[event_identity, list[move_key]]`
- Produces: `effective_n(cluster_size: int) -> float` default `1.0` when same event_identity (Kolari-style: treat as one cluster)

```python
def test_three_hundred_biotechs_count_as_one_cluster():
    atts = [{"event_identity": "fda:x", "move_key": str(i)} for i in range(300)]
    assert len(cluster_same_event(atts)) == 1
    assert effective_n(300) == 1.0
```

Full Ibragimov-Müller can wait for a later task with statsmodels; this task locks the **counting** invariant so p-values cannot pretend n=300.

- [ ] Commit `feat(heart): same-event cluster collapses effective n`

---

### Task 4: Human correction log

**Files:** `src/core/heart/corrections.py`, `tests/test_heart_corrections.py`

JSONL append-only `{move_key, previous_event, new_event, actor, at}` using the same lock pattern. Pytest cannot write production path.

- [ ] Commit `feat(heart): human attribution override ledger`

---

### Task 5: Ranking API

**Files:** `ranking.py` extend; `src/agent_server/heart_endpoints.py`; include router in `main.py` **only** `include_router`; `tests/test_heart_panel_api.py`

**Interfaces:**
- `rank_moves(rows: list[DailyMove], weights: RankingWeights) -> list[dict]`
- `GET /api/heart/ranking` returns JSON `{rows, weights, generated_at}`
- Empty store → `200` with `rows: []` and `error` omitted; missing backend → `503` with real error string

- [ ] Commit `feat(heart): ranking API on existing FastAPI`

---

### Task 6: Panel page

**Files:** `frontend/heart.html`, `frontend/js/heart_panel.js`; link from existing cockpit nav only if a single obvious nav file exists (do not redesign cockpit)

Load ranking JSON; table sortable; click row → evidence panel. Perspective optional in this task if JS bundle is heavy — first version: HTML table + fetch, Perspective as Task 7.

Playwright test: page shows "Indisponível" when API 503, never invents P&L.

- [ ] Commit `feat(heart): ranking page`

---

### Task 7: Perspective + chart markers (after table works)

Wire Perspective for 100k rows; lightweight-charts with event markers from Attribution.

Browser test with 1000 synthetic rows (not 100k in CI). Document 100k timing as a manual/ops check.

- [ ] Commit `feat(heart): perspective grid and event markers`

---

## Spec coverage

| Requirement | Task |
|---|---|
| Asymmetric window | 1 |
| Join + confidence | 2 |
| Cross-section | 3 |
| Human one-click | 4 |
| Ranking axes | 5 |
| Same FastAPI page | 6–7 |
| 100k rows | 7 (manual timing) |

**P3/P4 must not start implementation until P1 can emit DailyMove fixtures and P2 can emit MarketEvent fixtures.** Tasks 1–3 can be developed against **synthetic** fixtures immediately.
