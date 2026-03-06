# SuperEzio Operational UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake marketing frontpage with an operational SuperEzio console where visible market, decision, and journal states come from live backend calls or clearly labeled local browser state.

**Architecture:** Keep the existing FastAPI static frontend (`frontend/index.html`, `frontend/styles.css`, `frontend/app.js`) and wire it to the existing backend contracts: `/health`, `/product/manifest`, `/api/chart-data/{ticker}`, and `/task/submit`. Do not invent recommendations, tickers, confidence, evidence counts, or portfolio values. If no backend contract exists, render an honest empty or local-only state.

**Tech Stack:** FastAPI static files, vanilla HTML/CSS/JS, yfinance-backed chart endpoint, NDJSON streaming from `/task/submit`, localStorage for browser-local portfolio context and journal entries, pytest, Playwright CLI.

---

## File Structure

- Modify `frontend/index.html`: replace landing hero and static SNDL/SOFI/TLRY/WAIT preview with an app shell: live status, ticker controls, Radar, Decision Room, Evidence, Portfolio Context, and Journal.
- Modify `frontend/styles.css`: replace first-viewport marketing layout with dense operational panels, stable grid sizing, canvas chart area, stream log, and mobile layout.
- Modify `frontend/app.js`: add real fetch flow for health/manifest/chart data/task submit; parse NDJSON event types; draw chart from returned OHLCV; persist only user-entered portfolio context and saved decisions in localStorage.
- Modify `tests/test_agent_server_smoke.py`: assert operational UI contract and fake sample removal.
- Modify `tests/test_production_gate.py`: assert frontend is connected to live endpoints and does not contain sample decision values.

---

### Task 1: Lock The Anti-Fake UI Contract

**Files:**
- Modify: `tests/test_agent_server_smoke.py`
- Modify: `tests/test_production_gate.py`

- [ ] **Step 1: Change root smoke expectations**

Assert that `/` serves the operational console copy and no longer asserts the old marketing headline as the primary behavior:

```python
assert "SuperEzio Trust OS" in root.text
assert "Operational decision console" in root.text
assert "Financial decisions with auditable relief" not in root.text
```

- [ ] **Step 2: Require live endpoint hooks in frontend JS**

Assert that `frontend/app.js` references:

```python
for token in [
    "/api/chart-data/",
    "/task/submit",
    "PIPELINE_STEP",
    "DATA_COLLECTED",
    "EXPLANATION_CHUNK",
    "localStorage",
]:
    assert token in frontend_js.text
```

- [ ] **Step 3: Forbid fake sample decision values**

Assert that `frontend/index.html` does not contain:

```python
for token in ["SNDL today", "3 items matter", "14 evidence points", "8/12 consensus", "Confidence\\n                <strong>61%</strong>"]:
    assert token not in html
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_agent_server_smoke.py tests\test_production_gate.py -q
```

Expected before implementation: failures on old copy/static sample assertions.

---

### Task 2: Replace The Static Frontpage With An Operational Shell

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Replace hero preview with app controls**

Create first viewport sections with these stable IDs:

```html
<form id="market-form">...</form>
<section id="radar-panel">...</section>
<section id="decision-room">...</section>
<section id="evidence-panel">...</section>
<section id="portfolio-panel">...</section>
<section id="journal-panel">...</section>
```

- [ ] **Step 2: Add honest empty states**

Every panel must start with copy that describes no loaded data yet, for example:

```html
<p id="radar-empty">Load a ticker to fetch live chart data.</p>
<p id="decision-empty">Run Decision Room after market data loads.</p>
```

- [ ] **Step 3: Avoid invented financial values**

No ticker-specific recommendation, confidence, evidence count, or consensus count should exist in the HTML. Defaults can include only form defaults like `AAPL` as input value.

---

### Task 3: Implement Real Frontend Data Flow

**Files:**
- Modify: `frontend/app.js`

- [ ] **Step 1: Add chart loading**

Implement `loadMarketData(ticker, timeframe)`:

```javascript
const data = await fetchJson(`/api/chart-data/${encodeURIComponent(ticker)}?timeframe=${encodeURIComponent(timeframe)}`);
state.market = data;
renderMarketData(data);
drawPriceChart(data.ohlcv || []);
```

- [ ] **Step 2: Add chart context for `/task/submit`**

Implement `buildChartContext()` that includes ticker, timeframe, latest close/change, candle count, RSI/MACD availability, and source path `/api/chart-data/{ticker}`.

- [ ] **Step 3: Parse NDJSON events into visible state**

Handle at least:

```javascript
CHART_DATA, PIPELINE_STEP, DATA_COLLECTED, PENNYLAB_ANALYSIS, F51_VERDICT,
EXPERT_STARTED, EXPERT_DONE, MODEL_MISSING, CHUNK, EXPLANATION_CHUNK, ERROR, STREAM_END
```

- [ ] **Step 4: Implement real local journal**

Save only user-generated decision runs to:

```javascript
localStorage.setItem("superezio.journal.v1", JSON.stringify(entries));
```

Each entry must contain timestamp, ticker, prompt, answer, explanation, and event summary.

- [ ] **Step 5: Persist portfolio context honestly**

Save only user-entered cash, position, horizon, and risk tolerance to:

```javascript
localStorage.setItem("superezio.portfolio.v1", JSON.stringify(context));
```

Use it as optional prompt context; do not invent holdings.

---

### Task 4: Style The Console For Real Use

**Files:**
- Modify: `frontend/styles.css`

- [ ] **Step 1: Replace marketing layout**

Use a topbar plus app grid:

```css
.app-shell { display: grid; grid-template-columns: minmax(300px, 420px) minmax(0, 1fr); }
.console-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); }
```

- [ ] **Step 2: Stabilize operational panels**

Add fixed minimum dimensions for chart canvas, stream log, status chips, and journal rows so loading text and long model output do not resize controls.

- [ ] **Step 3: Add responsive behavior**

At `max-width: 900px`, collapse to one column and keep controls above results.

---

### Task 5: Verify With Tests And Browser

**Files:**
- Modify: product files only if verification reveals concrete bugs

- [ ] **Step 1: Run targeted pytest**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_agent_server_smoke.py tests\test_production_gate.py -q
```

Expected: pass.

- [ ] **Step 2: Run frontend browser flow**

Use Playwright CLI against:

```text
http://127.0.0.1:8002/
```

Flow:

1. Load page and verify title/content are operational console, not marketing.
2. Click load market data for `AAPL`.
3. Verify `/api/chart-data/AAPL` produces visible price/candle/evidence state.
4. Run Decision Room.
5. Verify `/task/submit` streams output and the Decision Room fills with real backend response.
6. Save to Journal and verify the journal row appears from localStorage.

- [ ] **Step 3: Run full regression**

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: all existing tests pass or only pre-existing unrelated lint/format issues remain.

---

## Self-Review

Spec coverage: removes fake sample values, wires live chart endpoint, preserves `/task/submit`, exposes pipeline event evidence, gives portfolio/journal usable behavior without pretending backend features exist.

Placeholder scan: no fake static ticker decisions, no TBD fields, no invented confidence.

Type consistency: IDs listed in `index.html` are consumed by `app.js`; tests reference literal endpoint hooks and sample-removal tokens.
