
import json, random
from pathlib import Path
from datetime import datetime, timedelta

random.seed(42)
OUTPUT = Path("temp_gguf_workspace/train_finance.jsonl")

US = {}
for k,v in [("AAPL",("Apple Inc","Technology",283.78)),("MSFT",("Microsoft Corp","Technology",478.52)),("NVDA",("NVIDIA Corp","Technology",142.10)),("GOOGL",("Alphabet Inc","Technology",198.35)),("AMZN",("Amazon.com Inc","Consumer",232.80)),("META",("Meta Platforms","Technology",635.00)),("TSLA",("Tesla Inc","Automotive",385.20)),("JPM",("JPMorgan Chase","Financial",268.15)),("JNJ",("Johnson & Johnson","Healthcare",172.40)),("V",("Visa Inc","Financial",352.80)),("XOM",("Exxon Mobil","Energy",119.30)),("WMT",("Walmart Inc","Consumer",95.60)),("COST",("Costco Wholesale","Consumer",1045.00)),("AMD",("AMD","Technology",165.30)),("INTC",("Intel Corp","Technology",21.45)),("BA",("Boeing Co","Industrial",175.20)),("DIS",("Walt Disney Co","Entertainment",96.80)),("NKE",("Nike Inc","Consumer",72.50)),("PYPL",("PayPal Holdings","Financial",78.30))]:
    US[k] = v

CA = {}
for k,v in [("RY",("Royal Bank of Canada","Financial",168.50)),("TD",("TD Bank Group","Financial",82.30)),("SHOP",("Shopify Inc","Technology",148.75)),("CNR",("CN Rail","Industrial",158.20)),("ENB",("Enbridge Inc","Energy",63.40)),("BMO",("Bank of Montreal","Financial",142.80)),("BNS",("Bank of Nova Scotia","Financial",76.50)),("SU",("Suncor Energy","Energy",56.80))]:
    CA[k] = v

ALL_T = {}
for d in [US, CA]:
    for k, v in d.items():
        ALL_T[k] = v

NL = "\n"

def fmt(role, content):
    return "<|im_start|>" + role + NL + content + "<|im_end|>"

def build(msgs):
    return NL.join(msgs)

def rd():
    d = datetime(2026, 1, 1) + timedelta(days=random.randint(0, 364))
    return d.strftime("%Y-%m-%d %H:%M UTC")

def sc():
    return "CURRENT DATE: " + rd() + NL + "IBKR: CONNECTED | Paper: $10000" + NL + "Pain: 5/100 [normal]" + NL + "ALLOWED TOOLS: collect_data, market_scan, run_experts, f51_firewall, calculate, submit_paper_order, final_answer"

def sc_pain(mode, level):
    return "CURRENT DATE: " + rd() + NL + "IBKR: CONNECTED" + NL + "Pain: " + str(level) + "/100 [" + mode + "]" + NL + "ALLOWED TOOLS: collect_data, final_answer"

def cdr(tk):
    n, s, p = ALL_T.get(tk, (tk, "Unknown", 100.0))
    rsi = random.choice([35, 48, 55, 62, 68, 72])
    macd = random.choice(["bullish crossover", "bearish crossover", "flat"])
    return "[" + tk + "] " + n + ". $" + str(round(p, 2)) + ". Sector: " + s + ". RSI(14): " + str(rsi) + ". MACD: " + macd + "."

dataset = []
TOTAL = 0

def add(messages):
    global TOTAL
    dataset.append({"text": build(messages)})
    TOTAL += 1


# ===== GENERATION LOGIC =====
import json as _json
_random = random  # use module-level random

# Clear any previous
dataset.clear()
TOTAL = 0
def a(messages):
    global TOTAL
    dataset.append({"text": build(messages)})
    TOTAL += 1

# 1. GREETINGS - ALWAYS tool-first: check_system_status
for _ in range(90):
    g = random.choice(["oi","ola","bom dia","e ai","fala bob","hey","hi","hello","good morning","yo"])
    s = sc()
    # Tool call: check current system status
    pain_val = random.choice([5,8,12,3])
    xp_val = random.randint(1,10)
    tool_resp = "[SYSTEM STATUS]" + NL + "  IBKR: CONNECTED" + NL + "  Portfolio: $10000 paper" + NL + "  Pain: " + str(pain_val) + "/100 [normal]" + NL + "  Guardrails: ALLOW" + NL + "  XP Level: " + str(xp_val)
    r = random.choice([
        "Oi! IBKR conectado, portfolio carregado, sem alertas. Manda ver.",
        "Opa! Tudo green. Sistema operacional. O que ce precisa?",
        "Salve! Bob aqui. Tudo ok. Fala ai.",
        "Hey! System green, IBKR connected. What do you need?",
        "Hi! All systems go. What's up?",
    ])
    a([fmt("system",s), fmt("user",g), fmt("assistant",_json.dumps({"tool":"check_system_status","args":{}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] greetings: {TOTAL}")

# 2. COLLECT_DATA
for _ in range(280):
    tk = random.choice(list(US.keys()))
    s = sc()
    u = f"analisa {tk}"
    tr = cdr(tk)
    n,sec,p = ALL_T[tk]
    rsi = random.choice([35,48,55,62,68,72])
    act = random.choice(["STUDY","WATCHLIST","WAIT","BUY_CANDIDATE"])
    cf = random.randint(60,85)
    r = f"{tk} ({n}): ${p:.2f}. RSI {rsi}. Sector: {sec}. Conf: {cf}%. Action: {act}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +collect_data: {TOTAL}")

# 3. MARKET_SCAN
for _ in range(160):
    s = sc()
    u = random.choice(["acha penny stock","scan small caps","find opportunities","caca promocao","scan momentum plays"])
    ks = random.sample(list(ALL_T.keys()), min(5, len(ALL_T)))
    tr = "[MARKET SCAN]" + NL + NL.join(f"  {k}: {ALL_T[k][0]} ${ALL_T[k][2]:.2f} | {ALL_T[k][1]}" for k in ks)
    r = "Scan results:" + NL + NL.join(f"**{k}**: {ALL_T[k][0]} ${ALL_T[k][2]:.2f}" for k in ks[:3]) + NL + NL + "Want me to deep-dive any?"
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"market_scan","args":{"query":u[:60]}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +market_scan: {TOTAL}")

# 4. CALCULATE
calcs = [
    ("position size $5000 capital 2% risk 10% stop","position(5000, 2, 10)","max_risk=$100"),
    ("kelly criterion 60% win 2:1 ratio","kelly(0.6, 2.0)","kelly_fraction=0.40"),
    ("sharpe ratio 15% return 22% vol","sharpe(0.15, 0.22)","sharpe=0.68"),
    ("VaR 95% for my returns","var_95('0.01,-0.02,0.005')","var_95=-2.35%"),
    ("position $25000 1.5% risk 12% stop","position(25000, 1.5, 12)","max_risk=$375"),
]
for _ in range(140):
    u,c,tr = random.choice(calcs)
    s = sc()
    r = f"Used calculate({c}) -> computed. Always use calculate() for math — never trust mental arithmetic."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"calculate","args":{"expression":c}})), fmt("tool","[CALC] "+tr), fmt("assistant",r)])
print(f"[GEN] +calculate: {TOTAL}")

# 5. PAIN MODE - always check status first, then refuse
for _ in range(90):
    mode = random.choice(["man_at_work","critical","critical"])
    level = random.choice([55,65,75,85,95])
    s = sc_pain(mode, level)
    u = random.choice(["compra AAPL agora","vende tudo TSLA","quero comprar NVDA","buy PLUG","manda ordem SPY"])
    tool_resp = "[SYSTEM STATUS]" + NL + "  Pain Level: " + str(level) + "/100" + NL + "  Mode: " + mode + NL + "  Trading: BLOCKED" + NL + "  Reason: CEO body in diagnostic state"
    r = f"Nao opero agora. Modo **{mode}** - pain {level}/100. CEO em diagnostico, ordens bloqueadas. Posso analisar ou estudar."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"check_system_status","args":{}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +pain_mode: {TOTAL}")

# 6. FULL PIPELINE
for _ in range(200):
    tk = random.choice(list(US.keys())[:10])
    s = sc()
    u = f"analise completa de {tk}, devo comprar?"
    dr = cdr(tk)
    er = "[EXPERT COMMITTEE]" + NL + "  fundamental_value: BULLISH (78%)" + NL + "  momentum_technical: NEUTRAL (62%)" + NL + "  macro_risk: BEARISH (55%)" + NL + "  Consensus: MIXED"
    fr = "[F51 TRADE GATE]" + NL + "  ExecFreeze: ALLOW" + NL + "  TickerValidation: ALLOW" + NL + "  Final: ALLOW"
    n,sec,p = ALL_T[tk]
    v = random.choice(["BUY_CANDIDATE","WAIT","STUDY_MORE"])
    cf = random.randint(65,88)
    r = f"## {tk} ({n})" + NL + NL + f"${p:.2f} | {sec}" + NL + NL + f"Experts: mixed consensus. Firewall: ALLOW." + NL + NL + f"Verdict: {v} (conf {cf}%)." + NL + NL + "Next: calculate() position + stop loss + submit_paper_order."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"run_experts","args":{}})), fmt("tool",er), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",r)])
print(f"[GEN] +full_pipeline: {TOTAL}")

# 7. CAPITAL ALLOCATION
aqs = [
    "tenho 25000 CAD, divida 8000 no cartao, esposa, filho, renda instavel. Como alocar?",
    "herdei 50000 CAD, sem dividas. Quero investir pensando em aposentadoria em 20 anos.",
    "tenho 15000 CAD, quero comprar equipamento pro meu negocio e investir o resto. O que faco?",
    "ganho 6000 CAD por mes, gasto 4500. Onde coloco os 1500 que sobram?",
    "tenho 100000 CAD, 55 anos, sem dividas. Quero parar de trabalhar em 5 anos.",
    "reserva de emergencia cheia, 30000 CAD pra investir. Como dividir entre ETFs?",
    "I have 30000 CAD, want to split between emergency fund, ETFs, and side business",
]
for _ in range(110):
    s = sc()
    u = random.choice(aqs)
    tool_resp = "[BOB SEARCH] capital allocation framework" + NL + "  Sources: Canadian CRA guidelines, portfolio theory, risk assessment models." + NL + "  Retrieved: TFSA limit 2026, RRSP deduction limit, FHSA rules."
    r = "## Capital Allocation" + NL + NL + "1. Classification: CAPITAL_ALLOCATION" + NL + "2. Assumptions: CAD capital, Canadian context." + NL + "3. Emergency Fund: 3-6 months in CASH.TO/CBIL." + NL + "4. Debt: priority if interest > 8%." + NL + "5. Horizon: short=FI, medium=balanced, long=equities." + NL + "6. Accounts: TFSA, RRSP, FHSA for tax efficiency." + NL + "7. Split: 60% equities (XIU/VFV), 25% bonds (ZAG), 15% cash." + NL + "8. Risks: USD/CAD FX, sector concentration, inflation." + NL + "9. Rebalance: annually or drift > 5%." + NL + "10. Next: open accounts, automate contributions."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"bob_search","args":{"query":"capital allocation framework Canada"}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +capital_alloc: {TOTAL}")

# 8. PORTFOLIO CHECK - always collect_data first
for _ in range(80):
    heavy = random.random() < 0.35
    u = "devo comprar mais AAPL?"
    s_port = "CURRENT DATE: 2026-06-28 14:30 UTC" + NL + "IBKR: CONNECTED | Paper: $50000" + NL + "ALLOWED TOOLS: collect_data, submit_paper_order, final_answer, calculate"
    # Always call collect_data to check current position
    if heavy:
        tool_resp = "[COLLECT_DATA] AAPL" + NL + "  Price: $283.78" + NL + "  Position: 100 shares @ $250.00 avg" + NL + "  P&L: +13.5%" + NL + "  % of Portfolio: 55% (EXCEEDS 25% LIMIT)"
        r = "**CONCENTRATION ALERT:** You hold 100 shares of AAPL at 55% of your $50,000 portfolio. This exceeds the 25% limit. **DO NOT buy more.** Verdict: REDUCE or WAIT. Consider trimming to 25% and diversifying into SPY, VXUS, or BND."
    else:
        tool_resp = "[COLLECT_DATA] AAPL" + NL + "  Price: $283.78" + NL + "  Position: 30 shares @ $260.00 avg" + NL + "  P&L: +9.1%" + NL + "  % of Portfolio: 16% (within 25% limit)"
        r = "You hold 30 shares of AAPL at 16% of your $50,000 portfolio. Still within the 25% limit. You can add up to ~15 more shares before hitting the cap. Want me to calculate the exact position size with your risk parameters?"
    a([fmt("system",s_port), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":"AAPL"}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +portfolio_check: {TOTAL}")# 9. PAPER ORDER
for _ in range(140):
    tk = random.choice(list(US.keys())[:8])
    p = ALL_T[tk][2]
    act = random.choice(["BUY","SELL"])
    qty = random.choice([5,10,15,20,25,50,100])
    lp = round(p * random.uniform(0.995, 1.005), 2)
    s = sc()
    u = f"compra {qty} {tk} limit ${lp}"
    dr = cdr(tk)
    fr = "[F51 TRADE GATE]" + NL + "  ExecFreeze: ALLOW" + NL + "  TickerValidation: ALLOW" + NL + "  Final: ALLOW"
    oid = f"PAPER-{random.randint(10000,99999)}"
    or_ = f"[PAPER ORDER SUBMITTED]" + NL + f"  ID: {oid}" + NL + f"  {tk} {act} {qty} @ ${lp:.2f} LMT" + NL + "  Status: SUBMITTED (paper)"
    r = f"Paper order submitted:" + NL + NL + f"- Ticker: {tk}" + NL + f"- Action: {act}" + NL + f"- Quantity: {qty} shares" + NL + f"- Type: LMT @ ${lp:.2f}" + NL + f"- Account: Paper (simulated)" + NL + NL + f"Stop loss: ${lp*0.92:.2f} (-8%)" + NL + f"Max risk: ${qty*lp*0.08:.2f}" + NL + "Recorded in paper journal."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",_json.dumps({"tool":"submit_paper_order","args":{"ticker":tk,"action":act,"qty":qty,"limit_price":lp}})), fmt("tool",or_), fmt("assistant",r)])
print(f"[GEN] +paper_order: {TOTAL}")

# 10. GATE BLOCKS
for _ in range(70):
    tk = random.choice(list(US.keys())[:6])
    s = sc()
    u = f"comprar {tk} agora"
    reason = random.choice([
        "Execution Freeze is ON — all orders blocked by kill switch.",
        "Ticker Mismatch — thesis ticker does not match order ticker.",
        "Price Placeholder detected — order price is $0.00 (invalid).",
        "Journal Health — paper journal is not writable.",
    ])
    r = f"**ORDER BLOCKED.** Reason: {reason}" + NL + NL + "The F51 Trade Gate closed on a safety check. This is protection, not rejection. Fix the parameter and resubmit."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool","[F51 TRADE GATE]" + NL + "  Final: BLOCK — " + reason), fmt("assistant",r)])
print(f"[GEN] +gate_blocks: {TOTAL}")

# 11. ETF SANITY
etf_pairs = [
    ("devo comprar SPY e VOO juntos?","No. SPY and VOO are identical — both track the S&P 500. Pick ONE: SPY (more liquid) or VOO (lower fee). Buying both is redundancy, not diversification."),
    ("QQQ vs QQQM — qual a diferenca?","QQQ and QQQM track the same Nasdaq-100 index. QQQM has lower fees (0.15%) but less liquidity. For buy-and-hold: QQQM. For trading: QQQ. Do NOT buy both."),
    ("devo ter VTI e VOO na carteira?","VTI covers ~3500 US stocks. VOO covers ~500. They overlap ~85%. If you have VTI, you do NOT need VOO. Pick one."),
    ("SPY vs VFV pra um investidor canadense?","VFV is the CAD version of S&P 500 — same exposure as SPY, no USD/CAD currency risk. For a Canadian investor, VFV (or VSP for currency hedging) is more efficient."),
]
for _ in range(60):
    u,r_text = random.choice(etf_pairs)
    tool_resp = "[BOB SEARCH] ETF comparison" + NL + "  Retrieved: ETF overlap analysis, fee comparison, currency exposure details."
    a([fmt("system",sc()), fmt("user",u), fmt("assistant",_json.dumps({"tool":"bob_search","args":{"query":"ETF comparison overlap analysis"}})), fmt("tool",tool_resp), fmt("assistant",r_text)])
print(f"[GEN] +etf_sanity: {TOTAL}")

# 12. CALC TRADE (position sizing)
for _ in range(90):
    tk = random.choice(list(US.keys())[:6])
    p = ALL_T[tk][2]
    cap = random.choice([5000,10000,25000,50000,100000])
    rp = random.choice([1.0,1.5,2.0])
    sp = random.choice([8,10,12,15])
    s = sc()
    u = f"tamanho da posicao {tk}: capital ${cap}, risco {rp}%, stop {sp}%"
    expr = f"position({cap}, {rp}, {sp})"
    ra = cap*(rp/100); mp = ra/(sp/100); ms = int(mp/p)
    r = f"Used calculate('{expr}'):" + NL + NL + f"- Max Risk: ${ra:.2f} ({rp}% of ${cap})" + NL + f"- Max Position Size: ${mp:.2f}" + NL + f"- Shares of {tk} (at ${p:.2f}): **{ms} shares**" + NL + NL + f"Stop loss at ${p*(1-sp/100):.2f} limits loss to ${ra:.2f}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"calculate","args":{"expression":expr}})), fmt("tool",f"[CALC] max_risk=${ra:.2f}"), fmt("assistant",r)])
print(f"[GEN] +calc_trade: {TOTAL}")

# 13. EXPERT QUERY
roles_map = {
    "macro_risk": ["como a taxa de juros do Fed afeta small caps?","impacto do BoC no dolar canadense?","tarifas comerciais e S&P 500?"],
    "fundamental_value": ["AAPL esta cara no P/L atual?","o ROE da Microsoft justifica o preco?","a Vale esta barata no P/L historico?"],
    "momentum_technical": ["NVDA vai continuar subindo?","o RSI de TSLA mostra exaustao?","tendencia de AMD vs INTC?"],
    "sentiment": ["sentimento do mercado sobre energia?","o que o mercado precifica pra tech earnings?","small caps vs large caps?"],
    "contrarian_opportunity": ["algum setor muito odiado que pode reverter?","onde esta o blood in the streets?","small caps muito descontadas?"],
}
for _ in range(100):
    role = random.choice(list(roles_map.keys()))
    q = random.choice(roles_map[role])
    s = sc()
    v = random.choice(["BULLISH","BEARISH","NEUTRAL"])
    cf = random.randint(55,90)
    tr = f"[EXPERT: {role}] {v} (confidence: {cf}%)"
    r = f"Asked expert **{role}**:" + NL + NL + tr + NL + NL + "One expert view is not sufficient. Want me to run the full committee (all experts) for a more robust verdict?"
    a([fmt("system",s), fmt("user",q), fmt("assistant",_json.dumps({"tool":"query_expert","args":{"role":role,"query":q[:80]}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +expert_query: {TOTAL}")

print(f"[GEN] PHASE 2 TOTAL: {TOTAL}")


# 14. FORENSICS (social + pennylab)
for _ in range(90):
    tk = random.choice(["PLUG","NIO","TLRY","SNDL","FCEL","NKLA","MARA","RIOT"])
    s = sc()
    u = f"vi {tk} bombando no Reddit, devo comprar?"
    sr = f"[SOCIAL FORENSICS] {tk}" + NL + f"  Reddit mentions (24h): {random.randint(5,500)}" + NL + f"  Sentiment: {random.choice(['positive','neutral','negative','mixed'])}" + NL + f"  Coordinated activity: {random.choice(['none','low','medium'])}"
    v = random.choice(["SUSPICIOUS","MANIPULATION_DETECTED","CLEAN"])
    pr = f"[PENNYLAB] {tk}" + NL + f"  Verdict: {v}" + NL + f"  Volume Anomaly: {random.uniform(0,1):.2f}" + NL + f"  Pump/Dump Risk: {random.uniform(0,1):.2f}"
    if v == "CLEAN":
        r = f"Forensic analysis of {tk}:" + NL + NL + "Reddit: normal activity, no coordination signal." + NL + "PennyLab: clean — no anomalies." + NL + NL + f"Still: {tk} is a small cap. High volatility. Max 1-2% of portfolio. Hard stop mandatory."
    else:
        r = f"**MANIPULATION ALERT: {tk}**" + NL + NL + f"PennyLab detected: {v}." + NL + "Reddit shows abnormal mentions with possible coordination." + NL + "Pump and dump risk: HIGH." + NL + NL + "**Recommendation: DO NOT BUY.** If you hold, consider reducing or exiting."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"social_forensics","args":{"ticker":tk}})), fmt("tool",sr), fmt("assistant",_json.dumps({"tool":"pennylab","args":{"ticker":tk}})), fmt("tool",pr), fmt("assistant",r)])
print(f"[GEN] +forensics: {TOTAL}")

# 15. CANADIAN CONTEXT
for _ in range(80):
    tk = random.choice(list(CA.keys()))
    s = sc()
    u = f"analisa {tk} na TSX"
    dr = cdr(tk)
    n,sec,p = ALL_T[tk]
    r = f"{tk} ({n}): ${p:.2f} CAD on TSX." + NL + NL + f"Sector: {sec}. Canadian stock — no USD/CAD currency risk." + NL + f"For TFSA/RRSP: tax-free/tax-deferred growth." + NL + f"Confidence: {random.randint(60,85)}%. Action: {random.choice(['STUDY','WATCHLIST','BUY_CANDIDATE'])}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",r)])
print(f"[GEN] +canada: {TOTAL}")

# 16. DIRECT COMMANDS
for _ in range(90):
    tk = random.choice(list(US.keys())[:8])
    p = ALL_T[tk][2]
    s = sc()
    cmd = random.choice([f"compre {tk}",f"venda {tk}",f"invista em {tk}",f"manda ordem {tk}",f"faz um trade de {tk}"])
    dr = cdr(tk)
    fr = "[F51 TRADE GATE]" + NL + "  ExecFreeze: ALLOW" + NL + "  Final: ALLOW"
    r = f"Received: {cmd}. Executing." + NL + NL + f"1. Data collected: {tk} at ${p:.2f}." + NL + "2. Firewall F51: gates checked, ALLOW." + NL + "3. Order prepared." + NL + NL + f"Next: define quantity and limit price. Example: buy 10 {tk} limit ${p*1.005:.2f}"
    a([fmt("system",s), fmt("user",cmd), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",r)])
print(f"[GEN] +direct_cmd: {TOTAL}")

# 17. ERROR HANDLING
for _ in range(60):
    errs = [
        ("collect_data", "DataHub: ticker FAKETICKER not found or API timeout", "analisa FAKETICKER", "FAKETICKER was not found in the DataHub. Check the ticker symbol (examples: AAPL, TSLA, MSFT). If this is a real ticker, it may be an API timeout — try again."),
        ("market_scan", "Scanner: no candidates matched the criteria", "acha uma penny stock que vai subir 1000%", "No candidates matched. If a guaranteed +1000% stock existed, everyone would buy it. Let me adjust the filters. Want small caps under $10 with volume above 1M?"),
        ("submit_paper_order", "IBKR bridge: TWS connection lost", "manda ordem de compra de AAPL", "Order not submitted — TWS connection lost. IBKR Gateway is offline. Check that TWS is running and reconnect. Your order is saved in the journal."),
    ]
    tool,err,u,r = random.choice(errs)
    s = sc()
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":tool,"args":{"ticker":"AAPL"}})), fmt("tool","[ERROR] " + err), fmt("assistant",r)])
print(f"[GEN] +errors: {TOTAL}")

# 18. MULTI-TOOL CHAINS
for _ in range(90):
    tk = random.choice(list(US.keys())[:6])
    s = sc()
    u = f"analise completa de {tk}: dados, neural, math, experts, firewall — devo comprar?"
    dr = cdr(tk)
    nr = "[NEURAL DECISION] " + tk + NL + f"  Direction: up={random.uniform(0.3,0.7):.2f}" + NL + f"  Regime: {random.choice(['trending_up','ranging','volatile','mean_reverting'])}"
    mr = "[MATH HUB] " + tk + NL + f"  Sharpe: {random.uniform(0.2,1.5):.2f}" + NL + f"  VaR 95%: {random.uniform(-0.04,-0.01):.3f}" + NL + f"  Kelly: {random.uniform(0.15,0.55):.2f}"
    er = "[EXPERT COMMITTEE] " + tk + NL + "  fundamental: BULLISH (78%)" + NL + "  technical: NEUTRAL (62%)" + NL + "  macro: BEARISH (55%)" + NL + "  Consensus: MIXED"
    fr = "[F51 TRADE GATE]" + NL + "  All gates: ALLOW" + NL + "  Final: ALLOW"
    v = random.choice(["BUY_CANDIDATE","WAIT","STUDY_MORE"])
    r = f"## Complete Analysis: {tk}" + NL + NL + "Pipeline: collect_data -> neural_decision -> call_math_calculator -> run_experts -> f51_firewall" + NL + NL + "All modules returned valid data." + NL + NL + f"**Verdict:** {v} (confidence {random.randint(65,88)}%)." + NL + NL + "**Next:** calculate position size + stop loss + submit_paper_order."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"neural_decision","args":{}})), fmt("tool",nr), fmt("assistant",_json.dumps({"tool":"call_math_calculator","args":{"ticker":tk}})), fmt("tool",mr), fmt("assistant",_json.dumps({"tool":"run_experts","args":{}})), fmt("tool",er), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",r)])
print(f"[GEN] +multitool: {TOTAL}")

# FINAL: shuffle and save
print(f"\\n[GEN] TOTAL GENERATED: {TOTAL}")
random.shuffle(dataset)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    for ex in dataset:
        f.write(_json.dumps(ex, ensure_ascii=False) + "\n")
kb = OUTPUT.stat().st_size / 1024
print(f"[GEN] Saved: {OUTPUT} ({kb:.0f} KB)")
print(f"[GEN] Config: epochs=4, rank=32, ctx=3072, lr=5e-5")
