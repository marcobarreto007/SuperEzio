# Investment QA Contract Hardening Implementation Plan

> **ATENÇÃO (atualizado 2026-08-26):** os scripts citados neste plano —
> `scripts/invest_api_qa.py` e `scripts/invest_qa.py` — **não existem mais** na
> árvore. Equivalentes atuais: `scripts/evaluate_investment_quality.py` e
> `scripts/investment_answer_quality.py`. Os passos deste plano histórico
> permanecem como registro do contrato de qualidade; antes de qualquer execução,
> mapear os passos para os scripts atuais.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Bob's investment QA route fail honestly, recover deterministically, and stop shipping malformed, fake-ticker, or ETF-overlap answers.

**Architecture:** Add a small pure investment-answer contract module, wire the QA scripts to it, then use deterministic fallbacks in the agent when the CEO cannot choose a tool or returns an unsafe investment answer. Prompt rules remain as guidance only; contracts and tests become the source of truth.

**Tech Stack:** Python 3.12, FastAPI `/task/submit` NDJSON stream, LangGraph pipeline nodes, Ruff, Pytest, Playwright smoke scripts.

---

## Current Evidence

- `scripts/invest_api_qa.py` currently reports `ok=true` for bad answers like `Bob could not finalize this answer` and `I couldn't decide on a tool`.
- Latest live report: `output/playwright/invest-api-qa-20260523-112426.json`.
- `Q1 capital_allocation`: bad fallback, 98 chars.
- `Q2 dividend/passive income`: bad fallback, 60 chars.
- `Q3 DCA/macro timing`: bad fallback, 60 chars.
- `Q4 AAPL concentration`: useful answer, but slow.
- `Q5 ETF comparison`: useful answer after dedup patch.

## File Structure

- Create: `src/core/pipeline/investment_quality.py`
  - Pure quality contract functions for investment answers.
  - No model calls, no network, no provider dependencies.
- Modify: `scripts/invest_api_qa.py`
  - Accumulate streamed chunks correctly.
  - Evaluate answer quality with `investment_quality`.
  - Exit nonzero on any failed QA case.
- Modify: `scripts/invest_qa.py`
  - Reuse the same quality contract for browser/UI QA.
- Modify: `src/core/pipeline/nodes/agent.py`
  - Add deterministic fallback for investment subclasses when CEO JSON/tool selection fails.
  - Apply minimal final-answer quality gate for high-confidence bad markers.
- Modify: `tests/contracts/test_contract_complex_finance.py`
  - Add contract tests for investment fallback behavior.
- Create: `tests/test_investment_quality.py`
  - Unit tests for fake ticker, fallback text, ETF overlap, and min-length quality gates.
- Update: `.f51/checkpoints/latest.json`
  - Record evidence and remaining risk after implementation.

---

### Task 1: Add Pure Investment Quality Contract

**Files:**
- Create: `src/core/pipeline/investment_quality.py`
- Test: `tests/test_investment_quality.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_investment_quality.py`:

```python
from src.core.pipeline.investment_quality import evaluate_investment_answer


def test_rejects_bad_fallback_text():
    result = evaluate_investment_answer(
        "I have $25,000 to invest. How should I allocate it?",
        "Bob could not finalize this answer. Try a narrower prompt.",
    )

    assert not result.ok
    assert "bad_fallback_text" in result.reasons


def test_rejects_could_not_decide_tool_text():
    result = evaluate_investment_answer(
        "Should I DCA or wait?",
        "I couldn't decide on a tool. The request might be malformed.",
    )

    assert not result.ok
    assert "bad_fallback_text" in result.reasons


def test_rejects_fake_ticker():
    result = evaluate_investment_answer(
        "Give me a portfolio allocation.",
        "Allocate 20% to VOOE as a money market ETF.",
    )

    assert not result.ok
    assert "fake_ticker:VOOE" in result.reasons


def test_rejects_spy_vti_overlap_in_allocation():
    result = evaluate_investment_answer(
        "Give me an allocation with percentages.",
        "Allocate 40% to SPY, 25% to VTI, 20% to BND, and 15% to cash.",
    )

    assert not result.ok
    assert "etf_overlap:SPY/VTI" in result.reasons


def test_allows_etf_comparison_without_overlap_failure():
    result = evaluate_investment_answer(
        "Compare VOO, VTI, and SCHD. Which one should I choose?",
        "VOO tracks the S&P 500. VTI covers the total US market. SCHD focuses on dividends. Recommendation: choose VTI for broad long-term exposure.",
    )

    assert result.ok
    assert result.reasons == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_investment_quality.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'src.core.pipeline.investment_quality'
```

- [ ] **Step 3: Implement pure contract module**

Create `src/core/pipeline/investment_quality.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
import re


BAD_FALLBACK_MARKERS = (
    "could not finalize this answer",
    "couldn't decide on a tool",
    "request might be malformed",
    "tool was already used",
    "blocked tool",
    "bob failed to produce a valid answer",
)

FAKE_TICKERS = ("VOOE", "SPYY", "VTII", "VXUSS", "BNDD", "SLVV", "QQQE", "SPYD")

OVERLAP_GROUPS = (
    ("SPY", "VTI", "VOO", "IVV"),
    ("QQQ", "QQQM"),
    ("VXUS", "VEU"),
)

COMPARISON_WORDS = ("compare", "comparison", "versus", " vs ", "difference between")


@dataclass(frozen=True)
class InvestmentQualityResult:
    ok: bool
    reasons: list[str]


def _contains_percentage_allocation(text: str) -> bool:
    return bool(re.search(r"\b\d{1,3}\s*%", text))


def _mentions_ticker(text: str, ticker: str) -> bool:
    return bool(re.search(rf"\b{re.escape(ticker)}\b", text, re.IGNORECASE))


def _is_comparison_question(question: str) -> bool:
    q = f" {question.lower()} "
    return any(word in q for word in COMPARISON_WORDS)


def evaluate_investment_answer(question: str, answer: str) -> InvestmentQualityResult:
    reasons: list[str] = []
    q = question or ""
    a = answer or ""
    lower = a.lower()

    if len(a.strip()) < 120:
        reasons.append("answer_too_short")

    if any(marker in lower for marker in BAD_FALLBACK_MARKERS):
        reasons.append("bad_fallback_text")

    for ticker in FAKE_TICKERS:
        if _mentions_ticker(a, ticker):
            reasons.append(f"fake_ticker:{ticker}")

    if _contains_percentage_allocation(a) and not _is_comparison_question(q):
        for group in OVERLAP_GROUPS:
            present = [ticker for ticker in group if _mentions_ticker(a, ticker)]
            if len(present) > 1:
                reasons.append(f"etf_overlap:{'/'.join(present)}")

    return InvestmentQualityResult(ok=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run unit tests**

Run:

```powershell
python -m pytest tests/test_investment_quality.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 5: Run lint on new module**

Run:

```powershell
python -m ruff check src/core/pipeline/investment_quality.py tests/test_investment_quality.py
python -m ruff format --check src/core/pipeline/investment_quality.py tests/test_investment_quality.py
```

Expected:

```text
All checks passed!
2 files already formatted
```

---

### Task 2: Make API QA Script Tell the Truth

**Files:**
- Modify: `scripts/invest_api_qa.py`
- Test: `python scripts/invest_api_qa.py`

- [ ] **Step 1: Add quality evaluation and correct chunk accumulation**

Modify `scripts/invest_api_qa.py`:

```python
from src.core.pipeline.investment_quality import evaluate_investment_answer
```

Inside `ask_one`, replace the current `final_text` overwrite logic with chunk accumulation:

```python
    text_parts: list[str] = []
```

When reading events:

```python
                            if isinstance(event, dict):
                                kind = event.get("kind") or event.get("type") or ""
                                text = event.get("final_content") or event.get("content") or ""
                                if kind == "CHUNK" and isinstance(text, str):
                                    text_parts.append(text)
                                elif isinstance(text, str) and text and not text_parts:
                                    text_parts.append(text)
```

After the stream ends:

```python
    final_text = "".join(text_parts)
    quality = evaluate_investment_answer(question, final_text)
```

Return:

```python
    return {
        "ok": quality.ok,
        "quality_reasons": quality.reasons,
        "wall_seconds": elapsed,
        "chunk_count": len(chunks),
        "final_text": final_text[:5000],
        "text_length": len(final_text),
    }
```

- [ ] **Step 2: Make script exit nonzero on failed cases**

At the end of `main`, after saving the report:

```python
    failed = [item for item in results if not item["result"].get("ok")]
    if failed:
        print("\nFAILED QA CASES:")
        for item in failed:
            print(f"- {item['question']}: {item['result'].get('quality_reasons')}")
        sys.exit(1)
```

- [ ] **Step 3: Run script against current server**

Run:

```powershell
python scripts/invest_api_qa.py
```

Expected before product fixes:

```text
FAILED QA CASES:
- I have $25,000 to invest: ['answer_too_short', 'bad_fallback_text']
- I want to build a passive income portfolio with dividend stocks: ['answer_too_short', 'bad_fallback_text']
- With current interest rates and market volatility in May 2026: ['answer_too_short', 'bad_fallback_text']
```

This failure is expected. Do not proceed until the script fails honestly.

---

### Task 3: Add Deterministic Investment Fallbacks

**Files:**
- Modify: `src/core/pipeline/nodes/agent.py`
- Test: `tests/contracts/test_contract_complex_finance.py`

- [ ] **Step 1: Write contract tests for deterministic fallback**

Append to `tests/contracts/test_contract_complex_finance.py`:

```python
def test_investment_fallback_capital_allocation_is_useful():
    from src.core.pipeline.nodes.agent import _investment_fallback_answer

    answer = _investment_fallback_answer(
        "I have $25,000 to invest. I am 35 years old, moderate risk tolerance. How should I allocate this capital?"
    )

    assert "CAPITAL_ALLOCATION" in answer
    assert "Final verdict:" in answer
    assert "Confidence:" in answer
    assert "could not finalize" not in answer.lower()
    assert "couldn't decide" not in answer.lower()
    assert len(answer) > 700


def test_investment_fallback_dividend_portfolio_is_useful():
    from src.core.pipeline.nodes.agent import _investment_fallback_answer

    answer = _investment_fallback_answer(
        "I want to build a passive income portfolio with dividend stocks for a Canadian investor."
    )

    assert "DIVIDEND_INCOME" in answer
    assert "TFSA" in answer or "RRSP" in answer
    assert "withholding" in answer.lower()
    assert "Final verdict:" in answer
    assert len(answer) > 700


def test_investment_fallback_dca_vs_wait_is_useful():
    from src.core.pipeline.nodes.agent import _investment_fallback_answer

    answer = _investment_fallback_answer(
        "Should I dollar-cost average into the market or wait for a correction?"
    )

    assert "DCA_VS_WAIT" in answer
    assert "Final verdict:" in answer
    assert "DCA" in answer
    assert len(answer) > 600
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/contracts/test_contract_complex_finance.py -q
```

Expected:

```text
ImportError or AttributeError for _investment_fallback_answer
```

- [ ] **Step 3: Implement `_investment_fallback_answer`**

Add near `_complex_finance_fallback_answer` in `src/core/pipeline/nodes/agent.py`:

```python
def _investment_fallback_answer(message: str) -> str:
    msg = (message or "").lower()

    if any(term in msg for term in ("dividend", "passive income", "income portfolio")):
        return (
            "1. **Question Classification** — DIVIDEND_INCOME.\n"
            "2. **Default recommendation** — Build dividend exposure through diversified, low-cost dividend or broad-market funds first; use individual dividend stocks only as satellite positions after diversification.\n"
            "3. **Canadian tax context** — Canadian eligible dividends can be tax-efficient in taxable accounts, while US dividends may face withholding tax. Account choice matters: TFSA, RRSP, RESP, or FHSA rules differ by household.\n"
            "4. **Allocation framework** — 60-80% diversified core ETF exposure, 10-25% dividend-focused ETF exposure, 0-15% individual dividend stocks only if the investor understands sector concentration.\n"
            "5. **Risk gates** — Avoid chasing yield, avoid single-sector bank/energy concentration, check payout sustainability, debt levels, dividend history, and liquidity.\n"
            "6. **Actionable next step** — Choose asset classes first, then verify any specific ticker with live data before buying.\n"
            "Final verdict: ETF_CORE_FIRST\n"
            "Confidence: 76"
        )

    if any(
        term in msg for term in ("dollar-cost", "dca", "wait for a correction", "market timing")
    ):
        return (
            "1. **Question Classification** — DCA_VS_WAIT.\n"
            "2. **Default recommendation** — Dollar-cost average instead of waiting for a perfect correction unless the money is needed within 12 months.\n"
            "3. **Why** — Waiting requires two correct decisions: when to stay out and when to re-enter. DCA reduces timing regret and spreads entry risk.\n"
            "4. **Practical schedule** — Deploy 25% now, then 25% every 30-45 days, while keeping emergency cash separate.\n"
            "5. **Risk gates** — Pause new equity buys if emergency reserves are below 3 months, if high-interest debt exists, or if the investment horizon is under 3 years.\n"
            "6. **What would change the answer** — A near-term cash need, job instability, high-interest debt, or a specific valuation/risk signal would shift more capital to cash or debt payoff.\n"
            "Final verdict: DCA\n"
            "Confidence: 74"
        )

    return _complex_finance_fallback_answer(message)
```

- [ ] **Step 4: Run contract tests**

Run:

```powershell
python -m pytest tests/contracts/test_contract_complex_finance.py -q
```

Expected:

```text
passed
```

---

### Task 4: Route CEO Tool-Selection Failure to Investment Fallback

**Files:**
- Modify: `src/core/pipeline/nodes/agent.py`
- Test: `tests/contracts/test_contract_complex_finance.py`

- [ ] **Step 1: Add test for bad CEO tool selection**

Append:

```python
@pytest.mark.asyncio
async def test_investment_prompt_no_tool_decision_gets_deterministic_fallback(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    class BadGateway:
        async def chat_completion(self, *args, **kwargs):
            return "not json"

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    result = await agent_module.node_agent(
        {
            "message": "I want to build a passive income portfolio with dividend stocks.",
            "route": "general",
            "intent": "general_question",
            "agent_iterations": 0,
        },
        gateway=BadGateway(),
    )

    assert "final" in result
    assert "DIVIDEND_INCOME" in result["final"]
    assert "couldn't decide" not in result["final"].lower()
```

- [ ] **Step 2: Run test to verify current failure**

Run:

```powershell
python -m pytest tests/contracts/test_contract_complex_finance.py::test_investment_prompt_no_tool_decision_gets_deterministic_fallback -q
```

Expected:

```text
FAIL because current fallback says "I couldn't decide on a tool"
```

- [ ] **Step 3: Replace malformed fallback branch**

In `src/core/pipeline/nodes/agent.py`, replace:

```python
content = (
    _complex_finance_fallback_answer(state.get("message", ""))
    if is_complex_finance
    else "I couldn't decide on a tool. The request might be malformed."
)
```

With:

```python
message = state.get("message", "")
content = (
    _investment_fallback_answer(message)
    if is_complex_finance
    or detect_complex_finance_intent(message)
    or detect_capital_allocation_intent(message)
    else "Bob could not choose a safe tool for this request. Please ask a narrower question."
)
```

Import the existing intent detectors from `src.core.pipeline.intents` if not already available in the file.

- [ ] **Step 4: Run targeted contract**

Run:

```powershell
python -m pytest tests/contracts/test_contract_complex_finance.py::test_investment_prompt_no_tool_decision_gets_deterministic_fallback -q
```

Expected:

```text
1 passed
```

---

### Task 5: Add High-Confidence Final Answer Quality Gate

**Files:**
- Modify: `src/core/pipeline/nodes/agent.py`
- Test: `tests/contracts/test_contract_complex_finance.py`

- [ ] **Step 1: Add test for fake ticker replacement**

Append:

```python
@pytest.mark.asyncio
async def test_investment_final_answer_with_fake_ticker_is_replaced(monkeypatch):
    from src.core.pipeline.nodes import agent as agent_module

    class FakeTickerGateway:
        async def chat_completion(self, *args, **kwargs):
            return (
                '{"tool":"final_answer","args":{"content":"Allocate 20% to VOOE and 80% to SPY."}}'
            )

    events = []
    monkeypatch.setattr(agent_module, "get_stream_writer", lambda: events.append)

    result = await agent_module.node_agent(
        {
            "message": "I have $25,000 to invest. Give me an allocation.",
            "route": "general",
            "intent": "general_question",
            "agent_iterations": 0,
        },
        gateway=FakeTickerGateway(),
    )

    assert "VOOE" not in result["final"]
    assert "CAPITAL_ALLOCATION" in result["final"]
```

- [ ] **Step 2: Implement quality gate before streaming final answer**

In the `final_answer` branch of `node_agent`, after `content` is extracted and after blank fallback handling, add:

```python
from ..investment_quality import evaluate_investment_answer

quality = evaluate_investment_answer(state.get("message", ""), str(content))
if not quality.ok and any(
    reason.startswith("fake_ticker:") or reason == "bad_fallback_text" for reason in quality.reasons
):
    content = _investment_fallback_answer(state.get("message", ""))
```

Do not replace answers only for `answer_too_short`; some direct answers can be short and valid.

- [ ] **Step 3: Run targeted test**

Run:

```powershell
python -m pytest tests/contracts/test_contract_complex_finance.py::test_investment_final_answer_with_fake_ticker_is_replaced -q
```

Expected:

```text
1 passed
```

---

### Task 6: Wire Browser QA to the Same Contract

**Files:**
- Modify: `scripts/invest_qa.py`

- [ ] **Step 1: Import evaluator**

Add:

```python
from src.core.pipeline.investment_quality import evaluate_investment_answer
```

- [ ] **Step 2: Evaluate each UI answer**

After extracting each answer text:

```python
quality = evaluate_investment_answer(question, answer_text)
result["ok"] = quality.ok
result["quality_reasons"] = quality.reasons
```

- [ ] **Step 3: Make script exit nonzero**

At the end:

```python
failed = [item for item in results if not item.get("ok")]
if failed:
    for item in failed:
        print(f"FAILED {item['id']}: {item.get('quality_reasons')}")
    raise SystemExit(1)
```

- [ ] **Step 4: Run browser QA only after API QA is green**

Run:

```powershell
python scripts/invest_qa.py --base-url http://127.0.0.1:8002
```

Expected:

```text
5/5 pass
```

---

### Task 7: Full Verification Gate

**Files:**
- Existing test and script files only.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest tests/test_investment_quality.py tests/contracts/test_contract_complex_finance.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run routing regression set**

Run:

```powershell
python -m pytest tests/test_market_scanner.py tests/test_agent_market_scan_loop.py tests/test_runtime_bob_fixes.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run full lint**

Run:

```powershell
python -m ruff check .
python -m ruff format --check .
```

Expected:

```text
All checks passed!
files already formatted
```

- [ ] **Step 4: Restart local API**

Use the existing local runtime method. Do not use GitHub or external deploy tooling.

Run:

```powershell
Get-NetTCPConnection -LocalPort 8002 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
```

Stop only the current API process if it is stale, then start:

```powershell
python -m agent_server.main
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8002
```

- [ ] **Step 5: Run live API QA**

Run:

```powershell
python scripts/invest_api_qa.py
```

Expected:

```text
5/5 pass
```

The report must show:

- no `could not finalize`
- no `couldn't decide`
- no `malformed`
- no `blocked tool`
- no fake ticker denylist hit
- no SPY/VTI/VOO percentage-overlap in capital allocation

- [ ] **Step 6: Run browser smoke**

Run:

```powershell
python scripts/browser_smoke.py --base-url http://127.0.0.1:8002
```

Expected:

```text
"ok": true
```

- [ ] **Step 7: Run full pytest**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
840+ passed
```

If the exact count changes because new tests were added, report the new count.

- [ ] **Step 8: Update checkpoint**

Update `.f51/checkpoints/latest.json` with:

- changed files
- focused tests
- full tests
- live API QA report path
- browser smoke screenshot/report path
- remaining risks

- [ ] **Step 9: Local commit only**

Because `.f51/GITHUB_POLICY.json` blocks GitHub, use local commit only.

Run:

```powershell
git status --short
git add src/core/pipeline/investment_quality.py src/core/pipeline/nodes/agent.py scripts/invest_api_qa.py scripts/invest_qa.py tests/test_investment_quality.py tests/contracts/test_contract_complex_finance.py .f51/checkpoints/latest.json
git commit -m "@ fix(investment): harden QA contracts and deterministic fallbacks"
```

Do not push.

---

## Self-Review

- Spec coverage: covers bad QA truthfulness, deterministic fallback, fake ticker handling, ETF overlap, API QA, browser QA, and checkpoint evidence.
- Placeholder scan: no TBD/TODO/implement-later placeholders.
- Type consistency: `InvestmentQualityResult.ok` and `.reasons` are used consistently by tests and scripts.
- Scope risk: this plan intentionally does not redesign scanner MRI; it only hardens investment QA correctness.
- Main risk: replacing final answers via quality gate must stay scoped to high-confidence bad markers, especially fake tickers and bad fallback text, to avoid suppressing valid short answers.

## Execution Recommendation

Use **inline execution** for Tasks 1-5 because the files are tightly coupled and the test cycle is short. Use a fresh verification pass for Tasks 6-7.
