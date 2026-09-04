"""Regression tests for the four pipeline defects measured on the real
2026-08-24 run ("cara pesquisa um papel pra investir" -> PAR, 248s):

1. Latency: LOCAL_MAX_TOKENS was 1024 and the final-answer generation alone
   took ~105s -> cap lowered to 700 (direct answer, ~30% faster).
2. Expert JSON corruption: key swaps (verdict written into "ticker"),
   malformed "}": "PAR", "verdict" fragments, and empty entries that
   surfaced as "? 0%" lines.
3. Truncation mid-word / spliced tails in Bob's final answer
   ("(-47.37%). igh", "...82.8%.Hub risk score is 0.00").
4. Empty expert rows in the /evidence HTML report.
"""

import asyncio
import logging
from pathlib import Path

import pytest

import src.core.pipeline.nodes.experts as experts_node
from core.evidence.report import generate_html_report
from core.evidence.run import EvidenceRun
from core.model_serving.providers import LOCAL_MAX_TOKENS
from core.pipeline.nodes.agent import _trim_to_sentence_boundary


def _noop_writer(_event: dict) -> None:
    return None


@pytest.fixture(autouse=True)
def _expert_collect_harness(monkeypatch):
    """node_collect_experts writes SSE events and reads learned weights —
    both are silenced so the tests exercise only the parser."""
    monkeypatch.setattr(experts_node, "get_stream_writer", lambda: _noop_writer)
    monkeypatch.setattr(experts_node, "get_effective_expert_weights", dict)


def _run_collect(state: dict) -> dict:
    return asyncio.run(experts_node.node_collect_experts(state))


# ── Defect 1: latency cap ──


def test_local_max_tokens_cap_is_1800():
    """Teto de max_tokens do provider local/agente.

    Era 700 (decisao de latencia do cerebro local em 2026-08-22: 1024 custava
    ~105s de um run de 248s; 700 mantinha a resposta direta e acima do piso de
    512). O swap b50aa70f passou o cerebro/agente para deepseek-v4-pro via API
    externa mantendo o prompt do CEO, e o teto subiu para o default DeepSeek
    (1800) — o provider local remanescente usa o mesmo valor. O pin guarda
    esse contrato vigente.
    """
    assert LOCAL_MAX_TOKENS == 1800


# ── Defect 2: expert JSON parsing ──


def test_swapped_ticker_verdict_keys_are_repaired():
    """The model wrote the verdict into "ticker" and left "verdict" missing
    ({"expert":"macro_risk","ticker":"CAUTIOUS","confidence":62,...}) — the
    verdict must be cooked back and the ticker restored from context."""
    result = _run_collect(
        {
            "run_id": "quality-swap-1",
            "route": "ticker_analysis",
            "ticker": "PAR",
            "expert_results": [
                {
                    "role": "macro_risk",
                    "ok": True,
                    "response": (
                        '{"expert":"macro_risk","ticker":"CAUTIOUS","confidence":62,'
                        '"top_signals":["CVaR tail loss"],"top_risks":["drawdown"],'
                        '"bob_readable":"PAR shows elevated tail risk."}'
                    ),
                }
            ],
        }
    )
    entry = result["expert_structured"]["macro_risk"]
    assert entry["verdict"] == "CAUTIOUS"
    assert entry["ticker"] == "PAR"
    assert entry["confidence"] == 62


def test_fully_swapped_keys_are_repaired():
    """Both fields swapped: "verdict" holds the ticker symbol and "ticker"
    holds the verdict enum value."""
    result = _run_collect(
        {
            "run_id": "quality-swap-2",
            "route": "ticker_analysis",
            "ticker": "PAR",
            "expert_results": [
                {
                    "role": "momentum_technical",
                    "ok": True,
                    "response": (
                        '{"expert":"momentum_technical","ticker":"BULLISH","verdict":"PAR",'
                        '"confidence":72,"bob_readable":"PAR is bullish."}'
                    ),
                }
            ],
        }
    )
    entry = result["expert_structured"]["momentum_technical"]
    assert entry["verdict"] == "BULLISH"
    assert entry["ticker"] == "PAR"


def test_valid_verdict_is_not_touched_by_the_repair():
    """A correct payload keeps ticker and verdict exactly as emitted."""
    result = _run_collect(
        {
            "run_id": "quality-swap-3",
            "route": "ticker_analysis",
            "ticker": "PAR",
            "expert_results": [
                {
                    "role": "macro_risk",
                    "ok": True,
                    "response": (
                        '{"expert":"macro_risk","ticker":"PAR","verdict":"CAUTIOUS",'
                        '"confidence":62,"bob_readable":"PAR shows elevated tail risk."}'
                    ),
                }
            ],
        }
    )
    entry = result["expert_structured"]["macro_risk"]
    assert entry["verdict"] == "CAUTIOUS"
    assert entry["ticker"] == "PAR"


def test_malformed_json_fragment_is_discarded_and_logged(caplog):
    """A broken "}": "PAR", "verdict" style fragment must never be stored in
    expert_structured nor echoed into the summary — only logged."""
    with caplog.at_level(logging.WARNING):
        result = _run_collect(
            {
                "run_id": "quality-malformed-1",
                "route": "ticker_analysis",
                "expert_results": [
                    {
                        "role": "contrarian_opportunity",
                        "ok": True,
                        "response": (
                            '{"expert":"contrarian","ticker":"PAR","verdict":"TRAP"'
                            '}": "PAR", "verdict":"NO_DATA"}'
                        ),
                    }
                ],
            }
        )
    assert "contrarian_opportunity" not in result["expert_structured"]
    assert "[INVALID_JSON] discarded" in result["expert_summary"]
    assert '}": "PAR"' not in result["expert_summary"]
    assert any("expert_json_discarded" in record.message for record in caplog.records)


def test_entry_without_verdict_and_without_bob_readable_is_discarded():
    """No verdict and no Bob-readable summary -> no content, no "? 0%" line."""
    result = _run_collect(
        {
            "run_id": "quality-empty-1",
            "route": "ticker_analysis",
            "expert_results": [
                {
                    "role": "macro_risk",
                    "ok": True,
                    "response": ('{"expert":"macro_risk","ticker":"PAR","confidence":62}'),
                }
            ],
        }
    )
    assert "macro_risk" not in result["expert_structured"]
    assert "[EMPTY] discarded" in result["expert_summary"]
    assert "? 0%" not in result["expert_summary"]


def test_question_mark_verdict_without_summary_is_discarded():
    """A literal "?" verdict with no summary is equally content-less."""
    result = _run_collect(
        {
            "run_id": "quality-empty-2",
            "route": "ticker_analysis",
            "expert_results": [
                {
                    "role": "macro_risk",
                    "ok": True,
                    "response": '{"expert":"macro_risk","ticker":"PAR","verdict":"?","confidence":0}',
                }
            ],
        }
    )
    assert "macro_risk" not in result["expert_structured"]


def test_valid_expert_contract_is_preserved():
    """A valid expert keeps the full contract keys:
    expert/ticker/verdict/confidence/top_signals/top_risks/bob_readable."""
    result = _run_collect(
        {
            "run_id": "quality-valid-1",
            "route": "ticker_analysis",
            "expert_results": [
                {
                    "role": "macro_risk",
                    "ok": True,
                    "response": (
                        '{"expert":"macro_risk","ticker":"PAR","verdict":"CAUTIOUS",'
                        '"confidence":62,"top_signals":["CVaR tail loss"],'
                        '"top_risks":["drawdown"],'
                        '"bob_readable":"PAR shows elevated tail risk."}'
                    ),
                }
            ],
        }
    )
    entry = result["expert_structured"]["macro_risk"]
    assert entry["expert"] == "macro_risk"
    assert entry["ticker"] == "PAR"
    assert entry["verdict"] == "CAUTIOUS"
    assert entry["confidence"] == 62
    assert entry["top_signals"] == ["CVaR tail loss"]
    assert entry["top_risks"] == ["drawdown"]
    assert entry["bob_readable"] == "PAR shows elevated tail risk."


# ── Defect 3: sentence-boundary trimmer ──


def test_trim_truncated_mid_word_to_complete_sentence():
    """Measured cut "...(-47.37%). igh" -> complete sentence."""
    assert _trim_to_sentence_boundary("queda de (-47.37%). igh") == "queda de (-47.37%)."


def test_trim_spliced_glued_tail():
    """Measured spliced tail "...82.8%.Hub risk score is 0.00" -> cut at the
    last sentence boundary."""
    assert (
        _trim_to_sentence_boundary(
            "...F51 gate did not clear with confidence 82.8%.Hub risk score is 0.00"
        )
        == "...F51 gate did not clear with confidence 82.8%."
    )


def test_trim_well_terminated_text_is_intact():
    text = "Compra com stop em 18.50."
    assert _trim_to_sentence_boundary(text) == text
    assert _trim_to_sentence_boundary("Sinal claro!") == "Sinal claro!"
    assert _trim_to_sentence_boundary("Risco alto?") == "Risco alto?"
    assert _trim_to_sentence_boundary("Linha 1\nLinha 2\n") == "Linha 1\nLinha 2"


def test_trim_short_fragment_without_punctuation_is_removed():
    assert _trim_to_sentence_boundary("fragmento") == ""
    assert _trim_to_sentence_boundary("") == ""
    assert _trim_to_sentence_boundary("   ") == "   "


def test_trim_long_prose_without_punctuation_is_kept():
    """A long punctuation-less tail is prose, not a max_tokens cut fragment —
    it must not be destroyed."""
    text = (
        "Fechou. O ativo caiu 5% hoje e os analistas seguem preocupados "
        "com a continuidade da queda no curto prazo"
    )
    assert _trim_to_sentence_boundary(text) == text


def test_trim_never_cuts_tool_call_json():
    """JSON tool calls (complete or truncated) are structured, not prose."""
    complete = 'NL text. {"tool":"final_answer","args":{"content":"answer here"}}'
    assert _trim_to_sentence_boundary(complete) == complete
    truncated = '{"tool":"final_answer","args":{"content":"queda de (-47.37%). igh'
    assert _trim_to_sentence_boundary(truncated) == truncated


# ── Defect 4: /evidence report renderer ──


def test_report_skips_empty_expert_rows(tmp_path):
    """Experts with no verdict AND no Bob-readable summary must not render
    as "? 0%" rows; experts with content keep their row."""
    run = EvidenceRun(prompt="test", ticker="PAR", run_id="quality-report-1")
    run.start()
    run.record_expert(
        expert_name="macro_risk",
        verdict="CAUTIOUS",
        confidence=0.62,
        provider="deepseek",
        bob_readable="PAR shows elevated tail risk.",
    )
    run.record_expert(
        expert_name="red_team_agent_1",
        verdict="?",
        confidence=0.0,
        provider="deepseek",
        bob_readable="",
    )
    report_path = Path(generate_html_report(run, tmp_path))
    html = report_path.read_text(encoding="utf-8")
    assert "macro_risk" in html
    assert "CAUTIOUS" in html
    assert "red_team_agent_1" not in html
    assert "? 0%" not in html
