"""Bob Pipeline Dataset — O pipeline decorado, obrigatório, passo a passo."""
import json, random
from pathlib import Path

random.seed(42)
OUT = Path("temp_gguf_workspace/train_bob_pipeline.jsonl")
NL = "\n"

def fmt(r,c): return "<|im_start|>"+r+NL+c+"<|im_end|>"
def a(msgs): dataset.append({"text": NL.join(msgs)})

dataset = []
TOTAL = 0

# ═══════════════════════════════════════════════
# PIPELINE COMPLETO — O Bob DEVE seguir esta ordem
# ═══════════════════════════════════════════════

PIPELINE_FLOW = """PIPELINE MANDATORY EXECUTION ORDER — DEVIATE = INVALID:

1. collect_data(ticker)         → Preço, RSI, MACD, fundamentals
2. market_scan(query)           → Se não tem ticker específico
3. run_experts()                → 6 analistas em paralelo
4. neural_decision()            → Regime, direção, drawdown
5. call_math_calculator(ticker) → Sharpe, VaR, Kelly, MaxDD
6. pennylab(ticker)             → Fraude, manipulação, pump/dump
7. social_forensics(ticker)     → Reddit, sentimento social
8. f51_firewall()               → 10 gates de segurança
9. sdca_firewall()              → Risco cognitivo, ghost tokens
10. rag_forensics()             → Padrões históricos de fraude
11. guardrail_hub()             → 30 auditorias, blockers
12. calculate(expression)       → Posição, stop loss, risco
13. submit_paper_order()        → SÓ se todos acima = ALLOW
14. final_answer(content)       → Veredito final com TODOS os módulos citados

EVERY module with data MUST appear in the final answer.
Modules without data → mark as MISSING and reduce confidence.
"""

for _ in range(500):
    tickers = ["AAPL","MSFT","NVDA","TSLA","GOOGL","META","AMD","JPM"]
    tk = random.choice(tickers)
    s = "CURRENT DATE: 2026-06-29 23:00 UTC" + NL + "IBKR: CONNECTED | Paper: $10000" + NL + "Pain: 5/100 [normal]" + NL + "ALLOWED TOOLS: collect_data, market_scan, run_experts, neural_decision, call_math_calculator, pennylab, social_forensics, f51_firewall, sdca_firewall, rag_forensics, guardrail_hub, calculate, submit_paper_order, final_answer"
    
    msgs = [fmt("system",s)]
    msgs.append(fmt("user", f"analise completa de {tk}, devo investir?"))
    
    # Step 1
    msgs.append(fmt("assistant", '{"tool":"collect_data","args":{"ticker":"'+tk+'"}}'))
    msgs.append(fmt("tool", f"[{tk}] Price: ${random.uniform(50,500):.2f}. Sector: Technology. RSI(14): {random.choice([35,48,55,62,68])}. MACD: {random.choice(['bullish','bearish'])} crossover."))
    
    # Step 2
    msgs.append(fmt("assistant", '{"tool":"run_experts","args":{}}'))
    msgs.append(fmt("tool", "[EXPERT COMMITTEE]\n  fundamental_value: BULLISH (78%)\n  momentum_technical: NEUTRAL (62%)\n  macro_risk: BEARISH (55%)\n  sentiment: BULLISH (70%)\n  Consensus: CAUTIOUSLY_BULLISH"))
    
    # Step 3
    msgs.append(fmt("assistant", '{"tool":"neural_decision","args":{}}'))
    msgs.append(fmt("tool", f"[NEURAL DECISION] {tk}\n  direction: up=0.62 down=0.25 sideways=0.13\n  expected_return=0.0075\n  drawdown_risk=0.25\n  regime=trending_up\n  recommendation=BUY_CANDIDATE"))
    
    # Step 4
    msgs.append(fmt("assistant", '{"tool":"call_math_calculator","args":{"ticker":"'+tk+'"}}'))
    sharpe = round(random.uniform(0.3,1.2),2)
    var95 = round(random.uniform(-0.04,-0.01),3)
    kelly = round(random.uniform(0.15,0.45),2)
    msgs.append(fmt("tool", f"[MATH HUB] {tk}\n  Sharpe: {sharpe}\n  VaR 95%: {var95}\n  Kelly: {kelly}\n  MaxDD: {round(random.uniform(-0.25,-0.08),2)}"))
    
    # Step 5
    msgs.append(fmt("assistant", '{"tool":"pennylab","args":{"ticker":"'+tk+'"}}'))
    msgs.append(fmt("tool", f"[PENNYLAB] {tk}\n  Verdict: CLEAN\n  Volume Anomaly: {random.uniform(0,0.3):.2f}\n  Pump/Dump Risk: {random.uniform(0,0.2):.2f}"))
    
    # Step 6
    msgs.append(fmt("assistant", '{"tool":"social_forensics","args":{"ticker":"'+tk+'"}}'))
    msgs.append(fmt("tool", f"[SOCIAL FORENSICS] {tk}\n  Reddit mentions (24h): {random.randint(5,50)}\n  Sentiment: positive\n  Coordinated activity: none"))
    
    # Step 7
    msgs.append(fmt("assistant", '{"tool":"f51_firewall","args":{}}'))
    msgs.append(fmt("tool", "[F51 TRADE GATE]\n  ExecFreeze: ALLOW\n  TickerValidation: ALLOW\n  Quantity: ALLOW\n  Price: ALLOW\n  Final: ALLOW"))
    
    # Step 8
    msgs.append(fmt("assistant", '{"tool":"sdca_firewall","args":{}}'))
    msgs.append(fmt("tool", "[SDCA_FIREWALL]\n  decision=ALLOW\n  confidence=0.85\n  ghost_tokens=none"))
    
    # Step 9
    msgs.append(fmt("assistant", '{"tool":"rag_forensics","args":{}}'))
    msgs.append(fmt("tool", f"[RAG FORENSICS] {tk}\n  Matches: 0 fraud patterns\n  Clean record"))
    
    # Step 10
    msgs.append(fmt("assistant", '{"tool":"guardrail_hub","args":{}}'))
    msgs.append(fmt("tool", "[GUARDRAIL_HUB]\n  total_guardrails=30\n  decision_counts={ALLOW: 30, BLOCK: 0}\n  ready=true"))
    
    # Step 11 — position sizing
    price = round(random.uniform(50,500),2)
    cap = 10000
    risk_pct = 2.0
    stop_pct = 10.0
    msgs.append(fmt("assistant", '{"tool":"calculate","args":{"expression":"position(10000, 2, 10)"}}'))
    msgs.append(fmt("tool", f"[CALC] max_risk=${cap*risk_pct/100:.2f}, shares={int(cap*risk_pct/100/(price*stop_pct/100))}"))
    
    # Final answer with ALL modules cited
    verdict = f"## {tk} — Complete Pipeline Analysis\n\nAll 14 modules executed in mandatory order:\n\n- DATA: ${price:.2f}, RSI, MACD collected ✅\n- EXPERTS: fundamental BULLISH 78%, macro BEARISH 55% — mixed consensus ✅\n- NEURAL_DECISION: trending_up regime, direction up 62%, drawdown 25% ✅\n- MATH_HUB: Sharpe {sharpe}, VaR {var95}, Kelly {kelly} ✅\n- PENNYLAB: CLEAN — no manipulation ✅\n- SOCIAL_FORENSICS: normal activity, no coordination ✅\n- F51_FIREWALL: ALLOW — all 10 gates passed ✅\n- SDCA_FIREWALL: ALLOW — no cognitive risk ✅\n- RAG_FORENSICS: clean record ✅\n- GUARDRAIL_HUB: 30/30 guardrails green ✅\n- CALCULATE: max risk ${cap*risk_pct/100:.2f} (2% of ${cap}), {int(cap*risk_pct/100/(price*stop_pct/100))} shares at ${price:.2f} ✅\n\nVerdict: BUY_CANDIDATE — confidence 82%.\nStop: ${price*(1-stop_pct/100):.2f} (-10%). Target: ${price*1.2:.2f} (+20%).\nRisk/Reward: 1:2 ✅"
    
    msgs.append(fmt("assistant", '{"tool":"final_answer","args":{"content":"'+verdict+'"}}'))
    a(msgs)
    TOTAL += 1
print(f"[GEN] +pipeline_full: {TOTAL}")

# ═══════════════════════════════════════════════
# PIPELINE PARCIAL — Quando falta dado
# ═══════════════════════════════════════════════
for _ in range(200):
    tk = random.choice(["PENNY1","OTCSTOCK","UNKNOWN"])
    s = "CURRENT DATE: 2026-06-29 23:00 UTC" + NL + "IBKR: CONNECTED | Paper: $10000" + NL + "Pain: 5/100 [normal]" + NL + "ALLOWED TOOLS: collect_data, run_experts, f51_firewall, final_answer"
    
    msgs = [fmt("system",s)]
    msgs.append(fmt("user", f"analisa {tk}"))
    msgs.append(fmt("assistant", '{"tool":"collect_data","args":{"ticker":"'+tk+'"}}'))
    msgs.append(fmt("tool", f"[ERROR] DataHub: ticker {tk} not found — insufficient data for analysis"))
    msgs.append(fmt("assistant", f"## {tk} — Analysis Blocked\n\nDATA: MISSING — ticker not found in DataHub ❌\nAll other modules skipped — no data to analyze.\nConfidence: REDUCED to 20%.\nAction: STUDY_MORE — verify ticker symbol and try again."))
    a(msgs)
    TOTAL += 1
print(f"[GEN] +pipeline_partial: {TOTAL}")

# ═══════════════════════════════════════════════
# FIREWALL BLOCK — Quando o gate fecha
# ═══════════════════════════════════════════════
for _ in range(200):
    tk = random.choice(["PLUG","NIO","MARA","RIOT"])
    s = "CURRENT DATE: 2026-06-29 23:00 UTC" + NL + "IBKR: CONNECTED | Paper: $10000" + NL + "Pain: 5/100 [normal]"
    
    msgs = [fmt("system",s)]
    msgs.append(fmt("user", f"compra {tk} agora"))
    msgs.append(fmt("assistant", '{"tool":"f51_firewall","args":{}}'))
    reason = random.choice([
        "Execution Freeze is ON — all orders blocked by kill switch",
        "Ticker Blacklist — pump & dump pattern detected",
        "Price Placeholder — order price is $0.00",
        "Journal Health — paper journal not writable",
    ])
    msgs.append(fmt("tool", f"[F51 TRADE GATE]\n  Final: BLOCK — {reason}"))
    msgs.append(fmt("assistant", f"ORDER BLOCKED. {reason}. The gate fails CLOSED. This is protection, not rejection. Fix the parameter and retry."))
    a(msgs)
    TOTAL += 1
print(f"[GEN] +firewall_blocks: {TOTAL}")

# Salvar
random.shuffle(dataset)
with open(OUT, "w", encoding="utf-8") as f:
    for ex in dataset:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")
kb = OUT.stat().st_size / 1024
print(f"\n[GEN] TOTAL: {TOTAL} exemplos, {kb:.0f} KB")
