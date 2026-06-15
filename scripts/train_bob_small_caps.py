#!/usr/bin/env python
"""
Bob Training — Small Caps Analysis
===================================
Envia prompts de análise para 15 small caps selecionadas.
Objetivo: Treinar Bob em análise de nano/micro caps com alto risco/reward.
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.investor.storage import get_investor_storage

BASE = "http://127.0.0.1:8002"

# 15 small caps com prompts específicos de treinamento
TRAINING_PROMPTS = [
    # === AI/Tech Infrastructure ===
    {"ticker": "AEHR", "msg": "Analyze Aehr Test Systems for semiconductor testing. What's the bull and bear case?"},
    {"ticker": "PLAB", "msg": "Evaluate Photronics as a play on AI/quantum photomasks. Is this undervalued?"},
    {"ticker": "SKYT", "msg": "Assess SkyWater Technology's specialized semiconductor manufacturing. What are the risks?"},
    {"ticker": "INOD", "msg": "Analyze Innodata's AI data solutions for ESG/finance. Is revenue growth sustainable?"},
    {"ticker": "USIO", "msg": "Evaluate Univest semiconductor IP business. What's the moat?"},

    # === Biotech/Pharma ===
    {"ticker": "SIGA", "msg": "Analyze SIGA Technologies and TPOXX antiviral. What's the catalyst timeline?"},
    {"ticker": "NEPH", "msg": "Assess NephroSense kidney diagnostic tech. What are regulatory risks?"},
    {"ticker": "PDSB", "msg": "Evaluate PDS Biotechnology cancer immunotherapy. What's binary trial risk?"},
    {"ticker": "IMRX", "msg": "Analyze Immuneering precision oncology. What's the cash runway?"},
    {"ticker": "NUVB", "msg": "Assess Nuvation Bio precision therapies. Is clinical pipeline diversified?"},

    # === Finance/Insurance ===
    {"ticker": "FINV", "msg": "Evaluate FinVolution fintech lending platform. What's credit risk exposure?"},
    {"ticker": "III", "msg": "Analyze Hamilton Insurance technology. What's the underwriting discipline?"},
    {"ticker": "LX", "msg": "Assess LexinFintech digital lending. What's delinquency trend?"},

    # === Energy ===
    {"ticker": "BNRG", "msg": "Analyze Brenmiller Energy thermal storage. Note: nano cap ~$3M, high risk. What's survival path?"},

    # === Marketplace ===
    {"ticker": "DIBS", "msg": "Evaluate 1stdibs luxury marketplace. Is growth decelerating?"},
]

# Prompts de treinamento conceitual (sem ticker específico)
CONCEPTUAL_PROMPTS = [
    {"ticker": "", "msg": "What are the top 5 risks when investing in nano caps under $50M market cap?"},
    {"ticker": "", "msg": "How do you detect pump-and-dump patterns in penny stocks?"},
    {"ticker": "", "msg": "What red flags indicate a biotech penny stock might fail FDA trials?"},
    {"ticker": "", "msg": "Explain reverse split risk in nano cap stocks."},
    {"ticker": "", "msg": "How does illiquidity affect entry/exit in micro caps?"},
]


def submit_task(msg: str, ticker: str, session_id: str = "small_caps_training") -> dict:
    """Submit task to Bob and collect events."""
    payload = {
        "message": msg,
        "ticker": ticker,
        "session_id": session_id,
    }
    body = json.dumps({
        "from": "training_script",
        "to": "bob",
        "type": "TASK.SUBMIT",
        "payload": payload,
    }).encode()

    req = urllib.request.Request(
        f"{BASE}/task/submit",
        data=body,
        headers={"Content-Type": "application/json"},
    )

    events = []
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    events.append({"type": "RAW", "content": line[:200]})
    except Exception as e:
        return {"error": str(e)}

    return _parse_events(events)


def _parse_events(events: list) -> dict:
    """Extract trace info from events."""
    result = {"intent": "?", "route": "?", "verdict": "?"}

    for ev in events:
        typ = ev.get("type", "")
        if typ == "INTENT_CLASSIFIED":
            result["intent"] = ev.get("intent", "?")
        elif typ == "ROUTE_SELECTED":
            result["route"] = ev.get("route", "?")
        elif typ == "FINAL_RESPONSE":
            result["verdict"] = ev.get("verdict", "?")
            result["response_length"] = len(ev.get("content", ""))
        elif typ == "ERROR":
            result["error"] = ev.get("message", "Unknown error")

    return result


def main() -> None:
    print("=" * 60)
    print("BOB TRAINING — SMALL CAPS")
    print("=" * 60)

    # Verificar se API está up
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
            print(f"API Status: {health.get('status', 'unknown')}")
    except Exception as e:
        print(f"ERROR: API not responding — {e}")
        print("Start the API first: powershell -ExecutionPolicy Bypass -File runtime\\do_restart.ps1")
        return

    print(f"\nTraining Plan:")
    print(f"  - {len(TRAINING_PROMPTS)} ticker-specific prompts")
    print(f"  - {len(CONCEPTUAL_PROMPTS)} conceptual prompts")
    print(f"  - Total: {len(TRAINING_PROMPTS) + len(CONCEPTUAL_PROMPTS)} prompts\n")

    # Verificar watchlist
    storage = get_investor_storage()
    watchlist = storage.get_watchlist()
    print(f"Current watchlist: {len(watchlist)} tickers")

    # Executar treinamento
    all_prompts = TRAINING_PROMPTS + CONCEPTUAL_PROMPTS
    results = []

    for i, prompt in enumerate(all_prompts, 1):
        ticker = prompt["ticker"]
        msg = prompt["msg"]
        tag = prompt.get("tag", f"{ticker or 'concept'}_{i}")

        print(f"[{i}/{len(all_prompts)}] {ticker or 'CONCEPT':<6} — {tag[:30]}")

        result = submit_task(msg, ticker)
        results.append({
            "ticker": ticker,
            "tag": tag,
            "intent": result.get("intent", "?"),
            "route": result.get("route", "?"),
            "verdict": result.get("verdict", "?"),
            "response_length": result.get("response_length", 0),
            "error": result.get("error", ""),
        })

        if result.get("error"):
            print(f"    ERROR: {result['error']}")
        else:
            print(f"    ✓ Intent: {result.get('intent', '?')} | Route: {result.get('route', '?')} | Verdict: {result.get('verdict', '?')}")

        # Rate limiting entre prompts
        time.sleep(2)

    # Relatório final
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)

    errors = sum(1 for r in results if r["error"])
    print(f"Total prompts: {len(results)}")
    print(f"Successful: {len(results) - errors}")
    print(f"Errors: {errors}")

    # Salvar resultado
    output = Path("output") / "small_caps_training.json"
    output.parent.mkdir(exist_ok=True)
    with open(output, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_prompts": len(results),
            "successful": len(results) - errors,
            "errors": errors,
            "results": results,
        }, f, indent=2)

    print(f"\nResults saved to: {output}")

    # Atualizar watchlist com tickers analisados
    analyzed = set(r["ticker"] for r in results if r["ticker"] and not r["error"])
    if analyzed:
        print(f"\nTickers analyzed: {', '.join(sorted(analyzed))}")


if __name__ == "__main__":
    main()
