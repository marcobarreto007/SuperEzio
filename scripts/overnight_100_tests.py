#!/usr/bin/env python
"""SuperEzio — 100 Testes de Investimento Overnight.
Do simples ao complexo. Todos os tipos de decisão.
Verifica se Bob usa o pipeline completo (MathHub, Experts, F51, Trinity, SDCA, Guardrails).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SERVER = "http://127.0.0.1:8002"
PROMPTS_DIR = Path("runtime/prompts")
RESULTS_FILE = Path("runtime/overnight_100_results.jsonl")

# -- 100 Test Cases: simples → complexo --------------------------
TESTS = [
    # === SIMPLES (1-15): Consultas básicas de ticker ===
    ("Qual o preço atual de AAPL?", "AAPL", ["price", "AAPL"]),
    ("MSFT price now?", "MSFT", ["price", "MSFT"]),
    ("How is GOOGL doing today?", "GOOGL", ["price", "GOOGL"]),
    ("TSLA última cotação", "TSLA", ["price", "TSLA"]),
    ("NVDA current market price", "NVDA", ["price", "NVDA"]),
    ("META stock price please", "META", ["price", "META"]),
    ("AMZN preço agora", "AMZN", ["price", "AMZN"]),
    ("What's BRK-B trading at?", "BRK-B", ["price", "BRK"]),
    ("JPM stock quote", "JPM", ["price", "JPM"]),
    ("Vale (VALE) cotação atual", "VALE", ["price", "VALE"]),
    ("Petrobras (PBR) price", "PBR", ["price", "PBR"]),
    ("NFLX current value", "NFLX", ["price", "NFLX"]),
    ("ADBE stock price", "ADBE", ["price", "ADBE"]),
    ("CRM price check", "CRM", ["price", "CRM"]),
    ("ORCL trading at what price?", "ORCL", ["price", "ORCL"]),

    # === ANÁLISE TÉCNICA (16-30): Indicadores ===
    ("AAPL análise técnica: RSI, MACD, tendência", "AAPL", ["RSI", "MACD", "tendência"]),
    ("MSFT technical analysis with RSI and moving averages", "MSFT", ["RSI", "SMA", "EMA"]),
    ("GOOGL RSI está sobrecomprado?", "GOOGL", ["RSI", "sobrecomprado"]),
    ("TSLA suporte e resistência", "TSLA", ["suporte", "resistência"]),
    ("NVDA MACD signal — buy or sell?", "NVDA", ["MACD", "sinal"]),
    ("META Bollinger Bands analysis", "META", ["Bollinger", "bandas"]),
    ("AMZN moving average crossover SMA20 vs SMA50", "AMZN", ["SMA20", "SMA50"]),
    ("AAPL tendência de curto prazo vs longo prazo", "AAPL", ["curto prazo", "longo prazo"]),
    ("Análise de volume para TSLA", "TSLA", ["volume"]),
    ("AAPL padrão de candles — último mês", "AAPL", ["candles", "padrão"]),
    ("MSFT força relativa vs SPY", "MSFT", ["força", "relativa"]),
    ("GOOGL momentum analysis", "GOOGL", ["momentum"]),
    ("NVDA VWAP e preço atual", "NVDA", ["VWAP"]),
    ("AAPL indicadores técnicos completos", "AAPL", ["RSI", "MACD", "EMA", "SMA"]),
    ("TSLA análise de volatilidade", "TSLA", ["volatilidade"]),

    # === RISK & RETURNS (31-45): Sharpe, VaR, Kelly ===
    ("AAPL Sharpe ratio e retorno ajustado ao risco", "AAPL", ["Sharpe", "retorno"]),
    ("MSFT Value at Risk (VaR 95%)", "MSFT", ["VaR", "Value at Risk"]),
    ("GOOGL Kelly fraction — quanto alocar?", "GOOGL", ["Kelly"]),
    ("TSLA max drawdown analysis", "TSLA", ["drawdown", "maximum"]),
    ("NVDA risk-adjusted performance", "NVDA", ["Sharpe", "Sortino"]),
    ("AAPL annualized return vs volatility", "AAPL", ["retorno", "volatilidade"]),
    ("Portfolio risk: 50% AAPL 50% MSFT", "AAPL", ["HRP", "portfolio"]),
    ("META drawdown histórico", "META", ["drawdown"]),
    ("AMZN return distribution analysis", "AMZN", ["retorno", "distribuição"]),
    ("Compare risco: AAPL vs TSLA vs NVDA", "AAPL", ["risco", "comparação"]),
    ("AAPL crisis score — está em crise?", "AAPL", ["crisis", "score"]),
    ("MSFT growth at risk assessment", "MSFT", ["growth", "risk"]),
    ("GOOGL systemic risk evaluation", "GOOGL", ["systemic", "risk"]),
    ("TSLA bubble risk — LPPLS analysis", "TSLA", ["bubble", "LPPLS"]),
    ("AAPL regime detection — bull or bear?", "AAPL", ["regime", "HMM", "Markov"]),

    # === VALUATION (46-55): DCF, valuation ===
    ("AAPL está caro ou barato? Análise de valuation", "AAPL", ["valuation", "DCF"]),
    ("MSFT intrinsic value vs market price", "MSFT", ["intrinsic", "valuation"]),
    ("GOOGL DCF valuation", "GOOGL", ["DCF", "valuation"]),
    ("TSLA fair value estimate", "TSLA", ["fair value"]),
    ("NVDA overvalued or undervalued?", "NVDA", ["overvalued", "undervalued"]),
    ("META price to earnings context", "META", ["valuation"]),
    ("AMZN growth vs value assessment", "AMZN", ["growth", "value"]),
    ("AAPL Shiller PE analysis", "AAPL", ["Shiller", "valuation"]),
    ("Qual ação está mais barata: AAPL ou MSFT?", "AAPL", ["barata", "valuation"]),
    ("VALE valuation vs Petrobras", "VALE", ["valuation", "comparação"]),

    # === SENTIMENT & NEWS (56-65): Sentimento ===
    ("AAPL market sentiment today", "AAPL", ["sentiment", "Genie"]),
    ("MSFT news sentiment analysis", "MSFT", ["sentiment", "news"]),
    ("GOOGL social media sentiment", "GOOGL", ["sentiment", "social"]),
    ("TSLA investor sentiment — bullish or bearish?", "TSLA", ["bullish", "bearish", "sentiment"]),
    ("NVDA market buzz analysis", "NVDA", ["sentiment", "market"]),
    ("AAPL Reddit sentiment", "AAPL", ["Reddit", "sentiment"]),
    ("Setor de tecnologia — sentimento geral", "AAPL", ["setor", "tecnologia", "sentiment"]),
    ("AAPL news impact on price", "AAPL", ["news", "impacto"]),
    ("MSFT analyst consensus", "MSFT", ["analyst", "consensus"]),
    ("AAPL earnings sentiment", "AAPL", ["earnings", "sentiment"]),

    # === CRISE & MACRO (66-75): Crise ===
    ("AAPL crisis resilience analysis", "AAPL", ["crisis", "resilience"]),
    ("MSFT credit risk assessment", "MSFT", ["credit", "risk"]),
    ("Risco de mercado macro para AAPL", "AAPL", ["macro", "risco"]),
    ("Inflação impacto nas techs (AAPL)", "AAPL", ["inflação", "macro"]),
    ("Interest rate impact on MSFT", "MSFT", ["interest rate", "macro"]),
    ("Recession risk for tech portfolio", "AAPL", ["recession", "risk"]),
    ("Minsky-Keen financial instability for AAPL", "AAPL", ["Minsky", "instability"]),
    ("Debt service ratio impact on markets", "AAPL", ["debt", "macro"]),
    ("Network contagion risk for banks vs tech", "AAPL", ["contagion", "network"]),
    ("Systemic bank risk vs tech sector AAPL", "AAPL", ["systemic", "bank"]),

    # === DECISÃO DE INVESTIMENTO (76-85): Trading ===
    ("Devo comprar AAPL agora? Análise completa", "AAPL", ["comprar", "recomendação"]),
    ("AAPL buy or sell recommendation with risk level", "AAPL", ["buy", "sell", "risk"]),
    ("MSFT investment thesis — long term", "MSFT", ["investment", "thesis", "long"]),
    ("GOOGL position sizing — quanto investir?", "GOOGL", ["position", "size"]),
    ("TSLA trade setup with entry and exit", "TSLA", ["entry", "exit", "setup"]),
    ("NVDA swing trade analysis", "NVDA", ["swing", "trade"]),
    ("AAPL vs MSFT vs GOOGL — qual melhor agora?", "AAPL", ["melhor", "comparação"]),
    ("Construir portfolio: 40% AAPL, 30% MSFT, 30% GOOGL", "AAPL", ["portfolio", "alocação"]),
    ("AAPL stop loss recommendation", "AAPL", ["stop loss"]),
    ("Recomendação de investimento para AAPL com todos os indicadores", "AAPL", ["recomendação", "todos"]),

    # === COMPLEXO (86-95): Multi-ticker, multi-factor ===
    ("Análise completa de AAPL: técnica, fundamental, risco, sentimento e valuation", "AAPL", ["técnica", "fundamental", "risco", "sentimento", "valuation"]),
    ("Multi-factor analysis MSFT with F51 verdict", "MSFT", ["F51", "multi-factor"]),
    ("AAPL investment decision with all guardrails", "AAPL", ["guardrails", "decisão"]),
    ("AAPL trinity deliberation — Genie + Deep consensus", "AAPL", ["Trinity", "Genie", "Deep"]),
    ("Expert committee review of TSLA", "TSLA", ["expert", "committee"]),
    ("AAPL neural decision forecast", "AAPL", ["neural", "forecast"]),
    ("AAPL SDCA firewall cognitive check", "AAPL", ["SDCA", "cognitive"]),
    ("AAPL RAG forensics — fraud check", "AAPL", ["RAG", "fraud", "forensics"]),
    ("AAPL full pipeline: MathHub → Experts → F51 → SDCA → Trinity → Guardrails", "AAPL", ["MathHub", "F51", "SDCA", "Trinity", "Guardrails"]),
    ("Análise AAPL como se eu fosse trader profissional com 10 anos de experiência", "AAPL", ["trader", "profissional"]),

    # === EDGE CASES (96-100): Casos extremos ===
    ("PETR4.SA análise completa", "PETR4.SA", ["price", "análise"]),
    ("VALE3.SA vs USIM5.SA — qual melhor?", "VALE3.SA", ["comparação"]),
    ("Crypto BTC-USD correlation with AAPL", "AAPL", ["correlation", "BTC"]),
    ("AAPL after hours impact analysis", "AAPL", ["after hours"]),
    ("AAPL complete investment report — all modules, all metrics, final verdict", "AAPL", ["complete", "all", "verdict"]),
]


def send_task(message: str, ticker: str = "", session_id: str = "") -> dict:
    """Send a task to the server and capture the full response."""
    payload = {
        "from": "overnight_test",
        "to": "superezio",
        "type": "TASK.SUBMIT",
        "payload": {
            "message": message,
            "ticker": ticker if ticker else "",
            "timeframe": "6M",
            "session_id": session_id or f"overnight_{int(time.time())}",
            "rigor": "strict",
            "memory_mode": "relevant_all",
        },
    }

    import urllib.request

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SERVER}/task/submit",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
    )

    events = []
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        return {"error": str(e), "events": events}

    # Extract key info
    result = {"events": events, "chunks": [], "run_id": "", "final_content": "", "error": None}

    for ev in events:
        t = ev.get("type", "")
        if t == "STREAM_START":
            result["run_id"] = ev.get("run_id", "")
        elif t == "CHUNK":
            result["chunks"].append(ev.get("content", ""))
        elif t == "STREAM_END":
            tr = ev.get("trace", {})
            result["intent"] = tr.get("detected_intent", "")
            result["ticker"] = tr.get("selected_ui_ticker", "")
            result["candidates"] = tr.get("candidate_count", 0)
            result["quality_score"] = tr.get("quality_score", 0)
            result["final_content_length"] = tr.get("final_content_length", 0)

    result["final_content"] = "".join(result["chunks"])
    return result


def check_prompt_for_terms(run_id: str, expected_terms: list[str]) -> dict:
    """Check if the saved prompt contains expected financial terms."""
    prompt_file = PROMPTS_DIR / f"{run_id}.txt"
    result = {"found": [], "missing": [], "prompt_exists": False}

    if prompt_file.exists():
        result["prompt_exists"] = True
        content = prompt_file.read_text(encoding="utf-8", errors="replace")
        content_upper = content.upper()
        for term in expected_terms:
            if term.upper() in content_upper:
                result["found"].append(term)
            else:
                result["missing"].append(term)
    else:
        # Try finding the latest prompt file
        if PROMPTS_DIR.exists():
            files = sorted(PROMPTS_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                result["prompt_exists"] = True
                content = files[0].read_text(encoding="utf-8", errors="replace")
                content_upper = content.upper()
                for term in expected_terms:
                    if term.upper() in content_upper:
                        result["found"].append(term)
                    else:
                        result["missing"].append(term)

    return result


def run_tests():
    """Run all 100 tests and save results."""
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    passed = 0
    failed = 0
    total_pipeline_terms_found = 0
    total_pipeline_terms_checked = 0

    print(f"=== SUPER EZIO 100 INVESTMENT TESTS ===")
    print(f"Start: {datetime.now(timezone.utc).isoformat()}")
    print(f"Server: {SERVER}")
    print(f"Tests: {len(TESTS)}")
    print()

    for i, (message, ticker, terms) in enumerate(TESTS, 1):
        label = f"[{i:03d}/100]"
        print(f"{label} {ticker:8s} | {message[:70]}...", end=" ", flush=True)

        t0 = time.time()
        result = send_task(message, ticker, session_id=f"overnight_{i:03d}")
        elapsed = time.time() - t0

        # Check if Bob responded
        has_response = len(result.get("final_content", "")) > 50
        has_error = result.get("error") is not None
        run_id = result.get("run_id", "")

        # Check prompt for expected terms
        prompt_check = {}
        if run_id:
            prompt_check = check_prompt_for_terms(run_id, terms)

        # Determine status
        ok = has_response and not has_error
        if ok:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        pipeline_hit = len(prompt_check.get("found", []))
        pipeline_miss = len(prompt_check.get("missing", []))
        total_pipeline_terms_found += pipeline_hit
        total_pipeline_terms_checked += pipeline_hit + pipeline_miss

        content_len = len(result.get("final_content", ""))
        intent = result.get("intent", "?")
        score = result.get("quality_score", 0)

        print(f"{status} | {elapsed:.1f}s | {content_len}c | intent={intent} | "
              f"terms={pipeline_hit}/{pipeline_hit + pipeline_miss} | score={score:.2f}")

        record = {
            "test": i,
            "ticker": ticker,
            "message": message,
            "status": "PASS" if ok else "FAIL",
            "elapsed_s": round(elapsed, 1),
            "content_length": content_len,
            "intent": intent,
            "quality_score": score,
            "run_id": run_id,
            "error": result.get("error"),
            "prompt_terms_found": prompt_check.get("found", []),
            "prompt_terms_missing": prompt_check.get("missing", []),
            "prompt_exists": prompt_check.get("prompt_exists", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        results.append(record)

        # Save incrementally
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # -- Summary --
    print()
    print(f"=== RESULTS ===")
    print(f"Total:   {len(TESTS)}")
    print(f"Passed:  {passed} PASS")
    print(f"Failed:  {failed} FAIL")
    print(f"Pipeline terms in prompt: {total_pipeline_terms_found}/{total_pipeline_terms_checked} "
          f"({100 * total_pipeline_terms_found / max(1, total_pipeline_terms_checked):.0f}%)")
    print(f"Results: {RESULTS_FILE}")

    # Write summary
    summary = {
        "total": len(TESTS),
        "passed": passed,
        "failed": failed,
        "pass_rate": round(100 * passed / len(TESTS), 1),
        "pipeline_terms_found": total_pipeline_terms_found,
        "pipeline_terms_checked": total_pipeline_terms_checked,
        "pipeline_hit_rate": round(100 * total_pipeline_terms_found / max(1, total_pipeline_terms_checked), 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    summary_file = RESULTS_FILE.with_suffix(".summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Summary: {summary_file}")

    return summary


if __name__ == "__main__":
    # Check server health
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"{SERVER}/health", timeout=5)
        health = json.loads(resp.read())
        print(f"Server health: {health.get('status', '?')}")
    except Exception as e:
        print(f"SERVER DOWN: {e}")
        print("Start the server first: PYTHONPATH=src python -m agent_server.main")
        sys.exit(1)

    run_tests()
