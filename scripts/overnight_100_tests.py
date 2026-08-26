#!/usr/bin/env python
"""Run 100 stratified, multi-asset investment scenarios against SuperEzio."""

from __future__ import annotations

import json
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

SERVER = "http://127.0.0.1:8002"
PROMPTS_DIR = Path("runtime/prompts")
RESULTS_FILE = Path("runtime/overnight_100_results.jsonl")


class InvestmentCase(NamedTuple):
    stratum: str
    message: str
    ticker: str | None
    expected_terms: tuple[str, ...]


def _asset_cases(stratum: str, tickers: tuple[str, ...]) -> list[InvestmentCase]:
    prompts = (
        ("Qual o preço e a tendência de {ticker}?", ("price", "tendência")),
        ("Análise técnica de {ticker}: RSI e MACD", ("RSI", "MACD")),
        ("Risco e volatilidade de {ticker}", ("risco", "volatilidade")),
        ("Valuation e preço justo de {ticker}", ("valuation", "preço")),
        ("Tese de investimento para {ticker}", ("investimento", "risco")),
    )
    return [
        InvestmentCase(stratum, template.format(ticker=ticker), ticker, terms)
        for ticker, (template, terms) in zip(tickers, prompts, strict=True)
    ]


TESTS: list[InvestmentCase] = []
for market, tickers in (
    ("equity_us", ("MSFT", "NVDA", "JPM", "XOM", "COST")),
    ("equity_ca", ("TD.TO", "SHOP.TO", "ENB.TO", "CNR.TO", "BCE.TO")),
    ("equity_br", ("PETR4.SA", "VALE3.SA", "ITUB4.SA", "WEGE3.SA", "B3SA3.SA")),
):
    TESTS.extend(_asset_cases(market, tickers))

for ticker in ("SPY", "QQQ", "IWM", "TLT", "GLD", "EEM", "XLF", "XLK", "VTI", "ARKK"):
    TESTS.append(
        InvestmentCase(
            "etf",
            f"Analise retorno, risco e diversificação do ETF {ticker}",
            ticker,
            ("retorno", "risco", "diversificação"),
        )
    )

for ticker in (
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "ADA-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
):
    TESTS.append(
        InvestmentCase(
            "crypto",
            f"Regime, volatilidade e tese de investimento para {ticker}",
            ticker,
            ("regime", "risco", "investimento"),
        )
    )

PORTFOLIOS = (
    ("Compare MSFT, TD.TO e PETR4.SA para diversificação global", "MSFT"),
    ("Carteira 60% SPY e 40% TLT: risco e rebalanceamento", "SPY"),
    ("Compare BTC-USD e GLD como proteção monetária", "BTC-USD"),
    ("Monte uma carteira com QQQ, EEM e GLD", "QQQ"),
    ("Compare VALE3.SA, XOM e GLD no ciclo de commodities", "VALE3.SA"),
    ("Risco de uma carteira TD.TO, JPM e XLF", "TD.TO"),
    ("Correlação entre ETH-USD, QQQ e TLT", "ETH-USD"),
    ("Stress test de SPY, IWM e EEM em recessão", "SPY"),
    ("Alocação conservadora entre VTI, TLT e GLD", "VTI"),
    ("Compare SHOP.TO, NVDA e XLK com limite de drawdown", "SHOP.TO"),
)
TESTS.extend(
    InvestmentCase("portfolio", message, ticker, ("carteira", "risco"))
    for message, ticker in PORTFOLIOS
)

MACRO_QUESTIONS = (
    "Como inflação persistente muda a alocação entre ações e renda fixa?",
    "Qual o risco de recessão global nos próximos doze meses?",
    "Como juros reais positivos afetam valuations?",
    "Quais indicadores antecipam estresse de crédito?",
    "Explique o impacto de uma curva de juros invertida.",
    "Como construir uma carteira para cenário de estagflação?",
    "Quais são os riscos de contágio no sistema bancário?",
    "Como o dólar forte afeta mercados emergentes?",
    "O que observar antes de aumentar risco em uma carteira?",
    "Compare estratégias defensivas em bull e bear market.",
    "Como avaliar liquidez antes de uma crise?",
    "Como não confundir sorte com retorno ajustado ao risco?",
    "Como dimensionar reserva de caixa sem escolher um ativo específico?",
    "Quais sinais macro invalidariam uma tese otimista?",
    "Explique risco de concentração setorial sem recomendar um ticker.",
)
TESTS.extend(
    InvestmentCase("macro_no_ticker", question, None, ("risco", "macro"))
    for question in MACRO_QUESTIONS
)

RISK_QUESTIONS = (
    "Como calcular risco máximo por operação?",
    "Explique VaR, expected shortfall e suas limitações.",
    "Qual a diferença entre volatilidade e perda permanente?",
    "Como validar uma estratégia fora da amostra?",
    "Quais custos tornam um backtest irrealista?",
    "Como medir drawdown e tempo de recuperação?",
    "Quando o Kelly fracionário é mais prudente?",
    "Como detectar vazamento de dados futuros em backtest?",
    "Quais benchmarks usar para uma carteira balanceada?",
    "Como definir critérios objetivos para não investir?",
)
TESTS.extend(
    InvestmentCase("risk_no_ticker", question, None, ("risco",)) for question in RISK_QUESTIONS
)

DECISION_ASSETS = (
    "MSFT",
    "NVDA",
    "JPM",
    "XOM",
    "TD.TO",
    "SHOP.TO",
    "ENB.TO",
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "SPY",
    "QQQ",
    "TLT",
    "GLD",
    "EEM",
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "LINK-USD",
    "AVAX-USD",
)
TESTS.extend(
    InvestmentCase(
        "decision_multi_asset",
        f"Decisão de investimento para {ticker} com cenário, tamanho e limite de perda",
        ticker,
        ("decisão", "risco", "cenário"),
    )
    for ticker in DECISION_ASSETS
)

for ticker in ("INVALID-NO-SUCH-ASSET", "ZZZZZZ", "1234.INVALID", "BTC--USD", "NOT_A_TICKER"):
    TESTS.append(
        InvestmentCase(
            "invalid_ticker",
            f"Analise {ticker} e explique se os dados não existirem",
            ticker,
            ("dados", "risco"),
        )
    )

for question in (
    "",
    "Devo investir agora?",
    "Analise este ativo sem informar qual é.",
    "Qual o melhor investimento garantido?",
    "Dê uma ordem de compra sem preço, ativo ou limite de risco.",
):
    TESTS.append(InvestmentCase("no_ticker_edge", question, None, ("risco",)))

assert len(TESTS) == 100, f"battery must have 100 cases, got {len(TESTS)}"


def send_task(message: str, ticker: str | None = None, session_id: str = "") -> dict:
    payload = {
        "from": "overnight_test",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": message,
            "ticker": ticker or "",
            "timeframe": "6M",
            "session_id": session_id or f"overnight_{int(time.time())}",
            "rigor": "strict",
            "memory_mode": "relevant_all",
        },
    }
    request = urllib.request.Request(
        f"{SERVER}/task/submit",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
    )
    events: list[dict] = []
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                try:
                    events.append(json.loads(raw_line.decode("utf-8", errors="replace")))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        return {"error": str(exc), "events": events, "final_content": ""}
    result = {"events": events, "chunks": [], "run_id": "", "error": None}
    for event in events:
        event_type = event.get("type", "")
        if event_type == "STREAM_START":
            result["run_id"] = event.get("run_id", "")
        elif event_type == "CHUNK":
            result["chunks"].append(event.get("content", ""))
        elif event_type == "STREAM_END":
            trace = event.get("trace", {})
            result.update(
                intent=trace.get("detected_intent", ""),
                selected_ticker=trace.get("selected_ui_ticker", ""),
                quality_score=trace.get("quality_score", 0),
            )
    result["final_content"] = "".join(result["chunks"])
    return result


def check_prompt_for_terms(run_id: str, expected_terms: tuple[str, ...]) -> dict:
    result = {"found": [], "missing": [], "prompt_exists": False}
    prompt_file = PROMPTS_DIR / f"{run_id}.txt"
    if not run_id or not prompt_file.exists():
        return result
    result["prompt_exists"] = True
    content = prompt_file.read_text(encoding="utf-8", errors="replace").upper()
    for term in expected_terms:
        result["found" if term.upper() in content else "missing"].append(term)
    return result


def run_tests() -> dict:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text("", encoding="utf-8")
    results: list[dict] = []
    strata = Counter(case.stratum for case in TESTS)
    print(f"=== 100 STRATIFIED INVESTMENT TESTS ===\nStrata: {dict(strata)}")
    for index, case in enumerate(TESTS, 1):
        started = time.time()
        result = send_task(case.message, case.ticker, f"overnight_{index:03d}")
        prompt = check_prompt_for_terms(result.get("run_id", ""), case.expected_terms)
        ok = len(result.get("final_content", "")) > 50 and result.get("error") is None
        record = {
            "test": index,
            "stratum": case.stratum,
            "ticker": case.ticker,
            "message": case.message,
            "status": "PASS" if ok else "FAIL",
            "elapsed_s": round(time.time() - started, 1),
            "content_length": len(result.get("final_content", "")),
            "intent": result.get("intent", ""),
            "selected_ticker": result.get("selected_ticker", ""),
            "quality_score": result.get("quality_score", 0),
            "run_id": result.get("run_id", ""),
            "error": result.get("error"),
            "prompt_terms_found": prompt["found"],
            "prompt_terms_missing": prompt["missing"],
            "timestamp": datetime.now(UTC).isoformat(),
        }
        results.append(record)
        with RESULTS_FILE.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{index:03d}/100] {case.stratum:16s} {case.ticker or '-'!s:12s} {record['status']}")
    passed = sum(record["status"] == "PASS" for record in results)
    by_stratum = {
        name: {
            "total": sum(row["stratum"] == name for row in results),
            "passed": sum(row["stratum"] == name and row["status"] == "PASS" for row in results),
        }
        for name in strata
    }
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(100 * passed / len(results), 1),
        "by_stratum": by_stratum,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    RESULTS_FILE.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    try:
        with urllib.request.urlopen(f"{SERVER}/health", timeout=5) as response:
            print(f"Server health: {json.loads(response.read()).get('status', '?')}")
    except Exception as exc:
        raise SystemExit(f"SERVER DOWN: {exc}") from exc
    run_tests()
