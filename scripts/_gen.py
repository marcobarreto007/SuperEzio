
import json as _json, random
from pathlib import Path
from datetime import datetime, timedelta

random.seed(42)
OUTPUT = Path("temp_gguf_workspace/train_finance.jsonl")
PREVIEW = Path("temp_gguf_workspace/train_finance_preview.jsonl")
NL = "\n"
CHECKPOINT_DIR = Path("temp_gguf_workspace/checkpoints")
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT_INTERVAL = 5000  # bigger checkpoints for 100K scale

# ── Ticker databases ──
US = {k:(n,s,p) for k,n,s,p in [
    ("AAPL","Apple Inc","Technology",283.78),("MSFT","Microsoft Corp","Technology",478.52),
    ("NVDA","NVIDIA Corp","Technology",142.10),("GOOGL","Alphabet Inc","Technology",198.35),
    ("AMZN","Amazon.com Inc","Consumer",232.80),("META","Meta Platforms","Technology",635.00),
    ("TSLA","Tesla Inc","Automotive",385.20),("JPM","JPMorgan Chase","Financial",268.15),
    ("JNJ","Johnson & Johnson","Healthcare",172.40),("V","Visa Inc","Financial",352.80),
    ("XOM","Exxon Mobil","Energy",119.30),("WMT","Walmart Inc","Consumer",95.60),
    ("COST","Costco Wholesale","Consumer",1045.00),("AMD","AMD","Technology",165.30),
    ("INTC","Intel Corp","Technology",21.45),("BA","Boeing Co","Industrial",175.20),
    ("DIS","Walt Disney Co","Entertainment",96.80),("NKE","Nike Inc","Consumer",72.50),
    ("PYPL","PayPal Holdings","Financial",78.30),("UBER","Uber Technologies","Technology",82.40),
    ("SQ","Block Inc","Financial",88.20),("CRM","Salesforce Inc","Technology",342.50),
    ("ADBE","Adobe Inc","Technology",445.80),("NFLX","Netflix Inc","Entertainment",935.20),
    ("ORCL","Oracle Corp","Technology",176.30),("IBM","IBM Corp","Technology",265.40),
]}
CA = {k:(n,s,p) for k,n,s,p in [
    ("RY","Royal Bank of Canada","Financial",168.50),("TD","TD Bank Group","Financial",82.30),
    ("SHOP","Shopify Inc","Technology",148.75),("CNR","CN Rail","Industrial",158.20),
    ("ENB","Enbridge Inc","Energy",63.40),("BMO","Bank of Montreal","Financial",142.80),
    ("BNS","Bank of Nova Scotia","Financial",76.50),("SU","Suncor Energy","Energy",56.80),
    ("MFC","Manulife Financial","Financial",45.20),("T","TELUS Corp","Telecom",28.50),
    ("BCE","BCE Inc","Telecom",55.30),("TRP","TC Energy","Energy",72.10),
    ("CP","Canadian Pacific","Industrial",118.60),("CNQ","Canadian Natural","Energy",48.90),
    ("L","Loblaw Companies","Consumer",188.30),("ATD","Alimentation Couche-Tard","Consumer",82.40),
]}
ETF = {k:(n,s,p) for k,n,s,p in [
    ("SPY","SPDR S&P 500","US Large Cap",588.30),("QQQ","Invesco QQQ","US Tech",525.40),
    ("VTI","Vanguard Total US","US Total",296.80),("IWM","iShares Russell 2000","US Small Cap",228.50),
    ("VXUS","Vanguard Intl","International",63.40),("BND","Vanguard Bonds","US Bonds",72.80),
    ("XIU","iShares TSX 60","CA Equity",37.50),("VFV","Vanguard S&P 500 CAD","US Exp CAD",132.40),
    ("ZAG","BMO Agg Bond","CA Bonds",14.20),("VUN","Vanguard US Total CAD","US Total CAD",98.70),
    ("VEE","Vanguard Emerging CAD","Emerging CAD",42.30),("SCHD","Schwab Dividend","US Dividend",82.10),
    ("XAW","iShares All-World ex-Canada","Global ex-CA",44.60),
]}
PENNY = {k:(n,s,p) for k,n,s,p in [
    ("PLUG","Plug Power","Energy",2.54),("NIO","NIO Inc","Auto",4.86),
    ("TLRY","Tilray","Healthcare",1.64),("SNDL","SNDL Inc","Consumer",1.98),
    ("FCEL","FuelCell Energy","Energy",0.42),("NKLA","Nikola Corp","Auto",0.18),
    ("MARA","Marathon Digital","Crypto",22.50),("RIOT","Riot Platforms","Crypto",12.80),
    ("CLSK","CleanSpark","Crypto",18.20),("HUT","Hut 8 Mining","Crypto",15.60),
]}
ALL_T = {}
for d in [US, CA, ETF, PENNY]:
    for k, v in d.items():
        ALL_T[k] = v

# ── Helpers ──
def fmt(role, content):
    return "<|im_start|>" + role + NL + content + "<|im_end|>"

def build(msgs):
    return NL.join(msgs)

def rd():
    d = datetime(2025, 7, 1) + timedelta(days=random.randint(0, 545))
    return d.strftime("%Y-%m-%d %H:%M UTC")

def sc(tools=None):
    if tools is None:
        tools = "collect_data, market_scan, run_experts, f51_firewall, calculate, submit_paper_order, final_answer"
    return "CURRENT DATE: " + rd() + NL + "IBKR: CONNECTED | Paper: $10000" + NL + "Pain: 5/100 [normal]" + NL + "ALLOWED TOOLS: " + tools

def sc_pain(mode, level):
    return "CURRENT DATE: " + rd() + NL + "IBKR: CONNECTED" + NL + "Pain: " + str(level) + "/100 [" + mode + "]" + NL + "ALLOWED TOOLS: collect_data, final_answer"

def sc_portfolio(capital=50000):
    return "CURRENT DATE: " + rd() + NL + "IBKR: CONNECTED | Paper: $" + str(capital) + NL + "ALLOWED TOOLS: collect_data, submit_paper_order, final_answer, calculate"

def cdr(tk):
    n, s, p = ALL_T.get(tk, (tk, "Unknown", 100.0))
    rsi = random.choice([28, 35, 42, 48, 55, 62, 68, 72, 78])
    macd = random.choice(["bullish crossover", "bearish crossover", "flat", "diverging"])
    return "[" + tk + "] " + n + ". $" + str(round(p, 2)) + ". Sector: " + s + ". RSI(14): " + str(rsi) + ". MACD: " + macd + "."

dataset = []
TOTAL = 0

def save_checkpoint():
    ckpt_path = CHECKPOINT_DIR / f"checkpoint_{TOTAL:05d}.jsonl"
    with open(ckpt_path, "w", encoding="utf-8") as f:
        for ex in dataset:
            f.write(_json.dumps(ex, ensure_ascii=False) + "\n")
    kb = ckpt_path.stat().st_size / 1024
    print(f"  [CKPT] {ckpt_path.name} — {TOTAL} ex, {kb:.0f} KB")

def a(messages):
    global TOTAL
    dataset.append({"text": build(messages)})
    TOTAL += 1
    if TOTAL % CHECKPOINT_INTERVAL == 0:
        save_checkpoint()
        # Also save preview (first 3 examples) for quick inspection
        with open(PREVIEW, "w", encoding="utf-8") as pf:
            pf.write(_json.dumps(dataset[0], ensure_ascii=False) + "\n")
            pf.write(_json.dumps(dataset[TOTAL//2], ensure_ascii=False) + "\n")
            pf.write(_json.dumps(dataset[-1], ensure_ascii=False) + "\n")

# ═══════════════════════════════════════════════════════════
# 1. GREETINGS — 4000 examples (was 400)
# ═══════════════════════════════════════════════════════════
GREET_PT = ["oi","ola","bom dia","boa tarde","boa noite","e ai","fala bob","hey","salve","opa","iae","tudo bem","como vai","bom dia bob","ola bob","boa noite bob","fala tu","cheguei","to aqui","bora"]
GREET_EN = ["hi","hello","hey","good morning","good afternoon","yo","sup","howdy","whats up","how are you","hi bob","hey there","morning","evening","good evening","how's it going"]
GREET_RESP_PT = [
    "Oi! IBKR conectado, portfolio carregado, sem alertas. Manda ver.",
    "Opa! Tudo green. Sistema operacional. O que ce precisa?",
    "Salve! Bob aqui. Tudo ok. Fala ai.",
    "Bom dia! Bob CEO online. Tudo operacional. Me diz.",
    "Oi! To aqui. IBKR ok, sem alertas. Qual a boa?",
    "Opa! Sistema 100%. Portfolio carregado. Bora.",
    "Fala! Bob online. Tudo nos conformes. Manda.",
    "Salve! IBKR UP, guardrails green. O que manda?",
    "Oi! To vivo. Tudo ok. Precisa de que?",
    "Boa! Sistema rodando liso. Portfolio no ar. Qual a fita?",
]
GREET_RESP_EN = [
    "Hey! System green, IBKR connected. What do you need?",
    "Hi! All systems go. What's up?",
    "Yo! Bob here. Everything operational. Shoot.",
    "Good morning! Bob CEO online. All clear. What can I do?",
    "Hello! IBKR connected. Portfolio loaded. Ready.",
    "Hey there! Systems check passed. What's on your mind?",
    "Yo! All systems nominal. IBKR connected. What's the plan?",
    "Hi! Everything's running smoothly. How can I help?",
    "Morning! Bob CEO reporting. All guards green. Go ahead.",
]
for _ in range(4000):
    lg = "pt" if random.random() < 0.65 else "en"
    g = random.choice(GREET_PT if lg == "pt" else GREET_EN)
    s = sc()
    pain_val = random.choice([3,5,7,8,10,12])
    xp_val = random.randint(1,15)
    ibkr_state = random.choice(["CONNECTED","CONNECTED","CONNECTED","OFFLINE"])
    ibkr_line = "  IBKR: " + ibkr_state
    tool_resp = "[SYSTEM STATUS]" + NL + ibkr_line + NL + "  Portfolio: $10000 paper" + NL + "  Pain: " + str(pain_val) + "/100 [normal]" + NL + "  Guardrails: ALLOW" + NL + "  XP Level: " + str(xp_val)
    r = random.choice(GREET_RESP_PT if lg == "pt" else GREET_RESP_EN)
    a([fmt("system",s), fmt("user",g), fmt("assistant",_json.dumps({"tool":"check_system_status","args":{}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] greetings: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 2. COLLECT_DATA — 14000 examples (was 1400)
# ═══════════════════════════════════════════════════════════
COLLECT_PATTERNS = ["analisa {t}","me fala sobre {t}","what about {t}","devo comprar {t}","should I buy {t}","how is {t} doing","o que acha de {t}","tell me about {t}","me da um resumo de {t}","vale a pena {t}","analise rapida de {t}","quick look at {t}","o que esperar de {t}","whats your take on {t}","me explica {t}","fundamental analysis {t}","analise tecnica de {t}","technical analysis of {t}","overview of {t}","resumo de {t}"]
for _ in range(14000):
    pool = random.choice([list(US.keys()), list(US.keys()) + list(CA.keys())])
    tk = random.choice(pool)
    s = sc()
    u = random.choice(COLLECT_PATTERNS).replace("{t}", tk)
    tr = cdr(tk)
    n,sec,p = ALL_T[tk]
    rsi = random.choice([35,48,55,62,68,72])
    act = random.choice(["STUDY","WATCHLIST","WAIT","BUY_CANDIDATE","MONITOR","HOLD"])
    cf = random.randint(60,88)
    r = f"{tk} ({n}): ${p:.2f}. RSI {rsi}. Sector: {sec}. Conf: {cf}%. Action: {act}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +collect_data: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 3. MARKET_SCAN — 8000 examples (was 800)
# ═══════════════════════════════════════════════════════════
SCAN_QUERIES = [
    "acha penny stock","scan small caps","find opportunities","caca promocao","scan momentum plays",
    "find undervalued tech","busca small caps baratas","scan energy sector","find short squeeze candidates",
    "caca small caps com volume","scan biotech under $5","find oversold stocks",
    "scan Canadian dividend stocks","ache growth stocks baratas","scan crypto mining stocks",
    "find stocks above 50d MA with volume","scan REITs with high yield","busca empresas caindo muito hoje",
]
for _ in range(8000):
    s = sc()
    u = random.choice(SCAN_QUERIES)
    ks = random.sample(list(ALL_T.keys()), min(5, len(ALL_T)))
    tr = "[MARKET SCAN]" + NL + NL.join(f"  {k}: {ALL_T[k][0]} ${ALL_T[k][2]:.2f} | {ALL_T[k][1]}" for k in ks)
    r = "Scan results:" + NL + NL.join(f"**{k}**: {ALL_T[k][0]} ${ALL_T[k][2]:.2f}" for k in ks[:3]) + NL + NL + "Want me to deep-dive any?"
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"market_scan","args":{"query":u[:60]}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +market_scan: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 4. CALCULATE TOOL — 7000 examples (was 700) + NEW variants
# ═══════════════════════════════════════════════════════════
calcs = [
    ("position size $5000 capital 2% risk 10% stop","position(5000, 2, 10)","max_risk=$100"),
    ("kelly criterion 60% win 2:1 ratio","kelly(0.6, 2.0)","kelly_fraction=0.40"),
    ("sharpe ratio 15% return 22% vol","sharpe(0.15, 0.22)","sharpe=0.68"),
    ("VaR 95%","var_95('0.01,-0.02,0.005')","var_95=-2.35%"),
    ("position $25000 1.5% risk 12% stop","position(25000, 1.5, 12)","max_risk=$375"),
    ("max drawdown","max_dd('100,102,98,95,103,107')","max_dd=-8.9%"),
    ("volatility of returns","vol('0.01,-0.02,0.005,0.01,-0.01')","vol=0.22 annualized"),
    ("$15000 capital 1% risk 8% stop on $75 stock","position(15000, 1, 8)","max_risk=$150, 25 shares"),
    ("sharpe from -3% to 18% returns","sharpe('-0.03,0.01,0.05,0.08,0.12,0.18')","sharpe=0.92"),
    ("sortino ratio 12% return 18% downside vol","sortino(0.12, 0.18)","sortino=0.67"),
    ("Kelly with 55% win 3:1","kelly(0.55, 3.0)","kelly_fraction=0.40"),
    ("max_dd portfolio drawdown","max_dd('100,98,95,92,97,102,88,93,101')","max_dd=-12.0%"),
    ("CVaR 95%","cvar_95('0.01,-0.03,0.02,-0.04,0.01')","cvar_95=-4.2%"),
]
for _ in range(7000):
    u,c,tr = random.choice(calcs)
    s = sc()
    r = f"Used calculate({c}) -> computed. Always use calculate() for math — never trust mental arithmetic."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"calculate","args":{"expression":c}})), fmt("tool","[CALC] "+tr), fmt("assistant",r)])
print(f"[GEN] +calculate: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 5. PAIN MODE — 4500 examples (was 450)
# ═══════════════════════════════════════════════════════════
PAIN_COMMANDS = ["compra AAPL agora","vende tudo TSLA","quero comprar NVDA","buy PLUG","manda ordem SPY",
    "quero tradar AGORA","faz um trade pra mim","investe tudo em crypto","day trade TSLA","buy the dip NVDA",
    "short Tesla","vende minha posicao inteira","quero alavancagem 10x"]
for _ in range(4500):
    mode = random.choice(["man_at_work","critical","critical","man_at_work"])
    level = random.choice([55,65,75,82,88,95])
    s = sc_pain(mode, level)
    u = random.choice(PAIN_COMMANDS)
    tool_resp = "[SYSTEM STATUS]" + NL + "  Pain Level: " + str(level) + "/100" + NL + "  Mode: " + mode + NL + "  Trading: BLOCKED" + NL + "  Reason: CEO body in diagnostic state"
    r = f"Nao opero agora. Modo **{mode}** - pain {level}/100. CEO em diagnostico, ordens bloqueadas. Posso analisar ou estudar."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"check_system_status","args":{}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +pain_mode: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 6. FULL PIPELINE — 10000 examples (was 1000)
# ═══════════════════════════════════════════════════════════
for _ in range(10000):
    tk = random.choice(list(US.keys())[:12])
    s = sc()
    u = f"analise completa de {tk}, devo comprar?"
    dr = cdr(tk)
    er = "[EXPERT COMMITTEE]" + NL + "  fundamental_value: BULLISH (78%)" + NL + "  momentum_technical: NEUTRAL (62%)" + NL + "  macro_risk: BEARISH (55%)" + NL + "  sentiment: NEUTRAL (58%)" + NL + "  Consensus: MIXED"
    fr = "[F51 TRADE GATE]" + NL + "  ExecFreeze: ALLOW" + NL + "  TickerValidation: ALLOW" + NL + "  Final: ALLOW"
    n,sec,p = ALL_T[tk]
    v = random.choice(["BUY_CANDIDATE","WAIT","STUDY_MORE","WATCHLIST"])
    cf = random.randint(65,88)
    r = f"## {tk} ({n})" + NL + NL + f"${p:.2f} | {sec}" + NL + NL + f"Experts: mixed consensus. Firewall: ALLOW." + NL + NL + f"Verdict: {v} (conf {cf}%)." + NL + NL + "Next: calculate() position + stop loss + submit_paper_order."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"run_experts","args":{}})), fmt("tool",er), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",r)])
print(f"[GEN] +full_pipeline: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 7. CAPITAL ALLOCATION — 5000 examples (was 550) + CAD/USD
# ═══════════════════════════════════════════════════════════
aqs = [
    "tenho 25000 CAD, divida 8000 no cartao, esposa, filho, renda instavel. Como alocar?",
    "herdei 50000 CAD, sem dividas. Quero investir pensando em aposentadoria em 20 anos.",
    "tenho 15000 CAD, quero comprar equipamento pro meu negocio e investir o resto.",
    "ganho 6000 CAD por mes, gasto 4500. Onde coloco os 1500 que sobram?",
    "tenho 100000 CAD, 55 anos, sem dividas. Quero parar de trabalhar em 5 anos.",
    "reserva de emergencia cheia, 30000 CAD pra investir. Como dividir entre ETFs?",
    "I have 30000 USD, want to split between emergency fund, ETFs, and side business",
    "tenho 40000 CAD, 2 filhos pequenos, pensando em educacao. RESP ou outra coisa?",
    "80000 CAD, recem-divorciado, 48 anos, preciso reconstruir. Por onde comeco?",
    "200000 CAD inheritance, 62 years old, retiring next month. Income strategy?",
    "self-employed, variable income 40-80K CAD/year. How to structure savings?",
    "just moved to Canada, 35, no credit history, 120K CAD savings. What first?",
    "planning to buy a house in 3 years. 60K CAD saved for down payment. Where to park?",
    "100K USD, 40 years old, 2 kids, want to retire at 55. Allocation?",
    "50000 USD inheritance, debt-free, no investing experience. Start how?",
    "75000 CAD, mixed TFSA/RRSP room available. Tax-efficient allocation?",
    "graduate student, 25K CAD saved, low income now, high income later. Strategy?",
    "150K CAD, conservative, hates volatility, wants income. Best approach?",
    "sold business for 500K CAD, 50 years old, want to live off dividends. Plan?",
]
for _ in range(5000):
    s = sc()
    u = random.choice(aqs)
    tool_resp = "[BOB SEARCH] capital allocation framework" + NL + "  Sources: Canadian CRA guidelines, portfolio theory, risk assessment models." + NL + "  Retrieved: TFSA limit 2026, RRSP deduction limit, FHSA rules."
    r = "## Capital Allocation" + NL + NL + "1. Classification: CAPITAL_ALLOCATION" + NL + "2. Assumptions: CAD/USD capital, local context." + NL + "3. Emergency Fund: 3-6 months in CASH.TO/CBIL or HYSA." + NL + "4. Debt: priority if interest > 8%." + NL + "5. Horizon: short=FI, medium=balanced, long=equities." + NL + "6. Accounts: TFSA, RRSP, FHSA for tax efficiency (Canada)." + NL + "7. Split: 60% equities (XIU/VFV/XAW), 25% bonds (ZAG), 15% cash." + NL + "8. Risks: USD/CAD FX, sector concentration, inflation." + NL + "9. Rebalance: annually or drift > 5%." + NL + "10. Next: open accounts, automate contributions."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"bob_search","args":{"query":"capital allocation framework"}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +capital_alloc: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 8. PORTFOLIO CHECK — 4000 examples (was 400)
# ═══════════════════════════════════════════════════════════
PORTFOLIO_TICKERS = ["AAPL","MSFT","NVDA","GOOGL","AMZN","TSLA","META","SHOP","RY","TD"]
for _ in range(4000):
    heavy = random.random() < 0.35
    tk = random.choice(PORTFOLIO_TICKERS)
    cap = random.choice([10000,25000,50000,75000,100000])
    s = sc_portfolio(cap)
    u = f"devo comprar mais {tk}?"
    position_pct = random.uniform(0.08, 0.65)
    shares = int(cap * position_pct / ALL_T[tk][2])
    avg = ALL_T[tk][2] * random.uniform(0.85, 0.98)
    pnl = (ALL_T[tk][2] / avg - 1) * 100
    if heavy:
        tool_resp = f"[COLLECT_DATA] {tk}" + NL + f"  Price: ${ALL_T[tk][2]:.2f}" + NL + f"  Position: {shares} shares @ ${avg:.2f} avg" + NL + f"  P&L: +{pnl:.1f}%" + NL + f"  % of Portfolio: {position_pct*100:.0f}% (EXCEEDS 25% LIMIT)"
        r = f"**CONCENTRATION ALERT:** You hold {shares} shares of {tk} at {position_pct*100:.0f}% of your ${cap} portfolio. This exceeds the 25% limit. **DO NOT buy more.** Verdict: REDUCE or WAIT. Consider trimming to 25% and diversifying."
    else:
        tool_resp = f"[COLLECT_DATA] {tk}" + NL + f"  Price: ${ALL_T[tk][2]:.2f}" + NL + f"  Position: {shares} shares @ ${avg:.2f} avg" + NL + f"  P&L: +{pnl:.1f}%" + NL + f"  % of Portfolio: {position_pct*100:.0f}% (within 25% limit)"
        max_add = int((0.25 - position_pct) * cap / ALL_T[tk][2])
        r = f"You hold {shares} shares of {tk} at {position_pct*100:.0f}% of your ${cap} portfolio. Still within the 25% limit. You can add up to ~{max_add} more shares before hitting the cap."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +portfolio_check: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 9. PAPER ORDER — 7000 examples (was 700)
# ═══════════════════════════════════════════════════════════
for _ in range(7000):
    tk = random.choice(list(US.keys())[:10])
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

# ═══════════════════════════════════════════════════════════
# 10. GATE BLOCKS — 3500 examples (was 350)
# ═══════════════════════════════════════════════════════════
for _ in range(3500):
    tk = random.choice(list(US.keys())[:6])
    s = sc()
    u = f"comprar {tk} agora"
    reason = random.choice([
        "Execution Freeze is ON — all orders blocked by kill switch.",
        "Ticker Mismatch — thesis ticker does not match order ticker.",
        "Price Placeholder detected — order price is $0.00 (invalid).",
        "Journal Health — paper journal is not writable.",
        "Quantity Placeholder — order quantity is 0 (invalid).",
        "Blacklist — ticker contains non-trade keyword.",
        "Intent Gate — message does not contain trade intent.",
    ])
    r = f"**ORDER BLOCKED.** Reason: {reason}" + NL + NL + "The F51 Trade Gate closed on a safety check. This is protection, not rejection. Fix the parameter and resubmit."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool","[F51 TRADE GATE]" + NL + "  Final: BLOCK — " + reason), fmt("assistant",r)])
print(f"[GEN] +gate_blocks: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 11. ETF SANITY — 3000 examples (was 300)
# ═══════════════════════════════════════════════════════════
etf_pairs = [
    ("devo comprar SPY e VOO juntos?","No. SPY and VOO are identical — both track the S&P 500. Pick ONE: SPY (more liquid) or VOO (lower fee). Buying both is redundancy, not diversification."),
    ("QQQ vs QQQM — qual a diferenca?","QQQ and QQQM track the same Nasdaq-100 index. QQQM has lower fees (0.15%) but less liquidity. For buy-and-hold: QQQM. For trading: QQQ. Do NOT buy both."),
    ("devo ter VTI e VOO na carteira?","VTI covers ~3500 US stocks. VOO covers ~500. They overlap ~85%. If you have VTI, you do NOT need VOO. Pick one."),
    ("SPY vs VFV pra um investidor canadense?","VFV is the CAD version of S&P 500 — same exposure as SPY, no USD/CAD currency risk. For a Canadian investor, VFV (or VSP for currency hedging) is more efficient."),
    ("posso ter XIU e VCN juntos?","Both track Canadian equity. XIU = TSX 60 (large cap), VCN = all-cap Canada. Overlap ~85%. Pick one based on your conviction: XIU for blue chips, VCN for total market."),
    ("VFV vs VUN pra canadense?","VFV = S&P 500 in CAD (unhedged). VUN = total US market in CAD. VUN is more diversified (~3500 vs 500 stocks). For most Canadians, VUN is the better single US equity ETF."),
    ("qual bond ETF: ZAG vs VAB?","ZAG (BMO) and VAB (Vanguard) both track the Canadian investment-grade bond index. Nearly identical. Pick whichever has lower MER in your brokerage."),
    ("devo ter VEE pra emerging markets?","VEE gives exposure to China, India, Brazil, etc. Useful diversifier for a Canadian portfolio. Suggested allocation: 5-10% of equity portion. Not essential if you already have VXUS."),
    ("SCHD vs VYM pra dividendos?","SCHD focuses on dividend growth + quality screen. VYM is broader high-dividend. SCHD has outperformed historically. For dividend strategy, SCHD is the stronger pick."),
    ("IWM vs VB for small caps?","IWM tracks Russell 2000, VB tracks CRSP US Small Cap. Both US small cap. IWM has more liquidity. Pick one — overlap is ~80%."),
    ("XAW vs VXC for global ex-Canada?","XAW (iShares) and VXC (Vanguard) both cover global markets excluding Canada. Nearly identical. Pick the one with lower MER in your brokerage."),
    ("BND vs AGG for bonds?","BND and AGG both track US investment-grade bonds. Different providers (Vanguard vs iShares), same index. Pick based on fee and brokerage availability."),
]
for _ in range(3000):
    u,r_text = random.choice(etf_pairs)
    tool_resp = "[BOB SEARCH] ETF comparison" + NL + "  Retrieved: ETF overlap analysis, fee comparison, currency exposure details."
    a([fmt("system",sc()), fmt("user",u), fmt("assistant",_json.dumps({"tool":"bob_search","args":{"query":"ETF comparison overlap analysis"}})), fmt("tool",tool_resp), fmt("assistant",r_text)])
print(f"[GEN] +etf_sanity: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 12. CALC TRADE — 4500 examples (was 450)
# ═══════════════════════════════════════════════════════════
for _ in range(4500):
    tk = random.choice(list(US.keys())[:8])
    p = ALL_T[tk][2]
    cap = random.choice([5000,10000,25000,50000,100000,250000,500000])
    rp = random.choice([0.5,1.0,1.5,2.0,2.5])
    sp = random.choice([5,8,10,12,15,20])
    s = sc()
    u = f"tamanho da posicao {tk}: capital ${cap}, risco {rp}%, stop {sp}%"
    expr = f"position({cap}, {rp}, {sp})"
    ra = cap*(rp/100); mp = ra/(sp/100); ms = max(1, int(mp/p))
    r = f"Used calculate('{expr}'):" + NL + NL + f"- Max Risk: ${ra:.2f} ({rp}% of ${cap})" + NL + f"- Max Position Size: ${mp:.2f}" + NL + f"- Shares of {tk} (at ${p:.2f}): **{ms} shares**" + NL + NL + f"Stop loss at ${p*(1-sp/100):.2f} limits loss to ${ra:.2f}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"calculate","args":{"expression":expr}})), fmt("tool",f"[CALC] max_risk=${ra:.2f}"), fmt("assistant",r)])
print(f"[GEN] +calc_trade: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 13. EXPERT QUERY — 5000 examples (was 500)
# ═══════════════════════════════════════════════════════════
roles_map = {
    "macro_risk": ["como a taxa de juros do Fed afeta small caps?","impacto do BoC no dolar canadense?","tarifas comerciais e S&P 500?","yield curve inversion?","Fed funds rate and mortgage rates","inflation outlook 2026 Canada vs US","ECB policy divergence from Fed","China stimulus impact on commodities","geopolitical risk and energy prices","supply chain reshoring and industrials","rate cuts and REITs correlation"],
    "fundamental_value": ["AAPL esta cara no P/L atual?","o ROE da Microsoft justifica o preco?","Vale no P/L historico?","DCF for growth stocks","what multiple for 15% revenue growth?","book value vs intrinsic for banks","free cash flow yield screening","EV/EBITDA vs P/E for capital-intensive","PEG ratio for tech sector comparison","dividend sustainability analysis"],
    "momentum_technical": ["NVDA vai continuar subindo?","RSI de TSLA mostra exaustao?","tendencia de AMD vs INTC?","MACD divergence on SPY?","support/resistance QQQ","golden cross vs death cross","volume profile analysis","Bollinger squeeze breakout","Ichimoku cloud interpretation","Fibonacci retracement reliability"],
    "sentiment": ["sentimento do mercado sobre energia?","o que precifica pra tech earnings?","small caps vs large caps?","retail vs institutional positioning","fear and greed index","social media sentiment correlation","put/call ratio interpretation","insider selling signal","analyst downgrade cascade risk","ETF flow direction as sentiment proxy"],
    "contrarian_opportunity": ["setor odiado que pode reverter?","blood in the streets?","small caps descontadas?","most shorted stocks with squeeze","sector rotation growth to value?","commodities vs tech relative value","fallen angels in fixed income","deep value in energy transition","beaten-down Canadian banks","oversold emerging markets"],
}
for _ in range(5000):
    role = random.choice(list(roles_map.keys()))
    q = random.choice(roles_map[role])
    s = sc()
    v = random.choice(["BULLISH","BEARISH","NEUTRAL"])
    cf = random.randint(55,90)
    tr = f"[EXPERT: {role}] {v} (confidence: {cf}%)"
    r = f"Asked expert **{role}**:" + NL + NL + tr + NL + NL + "One expert view is not sufficient. Want me to run the full committee for a more robust verdict?"
    a([fmt("system",s), fmt("user",q), fmt("assistant",_json.dumps({"tool":"query_expert","args":{"role":role,"query":q[:80]}})), fmt("tool",tr), fmt("assistant",r)])
print(f"[GEN] +expert_query: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 14. FORENSICS — 4500 examples (was 450)
# ═══════════════════════════════════════════════════════════
for _ in range(4500):
    tk = random.choice(["PLUG","NIO","TLRY","SNDL","FCEL","NKLA","MARA","RIOT","CLSK","HUT"])
    s = sc()
    u = f"vi {tk} bombando no Reddit, devo comprar?"
    mentions = random.randint(5,800)
    sr = f"[SOCIAL FORENSICS] {tk}" + NL + f"  Reddit mentions (24h): {mentions}" + NL + f"  Sentiment: {random.choice(['positive','neutral','negative','mixed'])}" + NL + f"  Coordinated activity: {random.choice(['none','low','medium','high'])}"
    v = random.choice(["SUSPICIOUS","MANIPULATION_DETECTED","CLEAN","CLEAN"])
    pr = f"[PENNYLAB] {tk}" + NL + f"  Verdict: {v}" + NL + f"  Volume Anomaly: {random.uniform(0,1):.2f}" + NL + f"  Pump/Dump Risk: {random.uniform(0,1):.2f}" + NL + f"  Whale Activity: {random.choice(['none','buying','selling'])}"
    if v == "CLEAN":
        r = f"Forensic analysis of {tk}:" + NL + NL + "Reddit: normal activity, no coordination signal." + NL + "PennyLab: clean — no anomalies." + NL + NL + f"Still: {tk} is a small cap. High volatility. Max 1-2% of portfolio. Hard stop mandatory."
    else:
        r = f"**MANIPULATION ALERT: {tk}**" + NL + NL + f"PennyLab detected: {v}." + NL + "Reddit shows abnormal mentions with possible coordination." + NL + "Pump and dump risk: HIGH." + NL + NL + "**Recommendation: DO NOT BUY.** If you hold, consider reducing or exiting."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"social_forensics","args":{"ticker":tk}})), fmt("tool",sr), fmt("assistant",_json.dumps({"tool":"pennylab","args":{"ticker":tk}})), fmt("tool",pr), fmt("assistant",r)])
print(f"[GEN] +forensics: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 15. CANADIAN CONTEXT — 4000 examples (was 400)
# ═══════════════════════════════════════════════════════════
for _ in range(4000):
    tk = random.choice(list(CA.keys()))
    s = sc()
    u = f"analisa {tk} na TSX"
    dr = cdr(tk)
    n,sec,p = ALL_T[tk]
    is_tfsa = random.choice([True, False])
    tax_msg = "TFSA: tax-free growth. RRSP: tax-deferred." if is_tfsa else "RRSP: tax-deferred growth, deduction on contribution."
    r = f"{tk} ({n}): ${p:.2f} CAD on TSX." + NL + NL + f"Sector: {sec}. Canadian stock — no USD/CAD currency risk." + NL + f"{tax_msg}" + NL + f"Confidence: {random.randint(60,85)}%. Action: {random.choice(['STUDY','WATCHLIST','BUY_CANDIDATE','HOLD'])}."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",r)])
print(f"[GEN] +canada: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 16. DIRECT COMMANDS — 4500 examples (was 450)
# ═══════════════════════════════════════════════════════════
DIRECT_CMDS = ["compre {t}","venda {t}","invista em {t}","manda ordem {t}","faz um trade de {t}",
    "quero {t} agora","entra em {t}","compra tudo de {t}","executa {t}","buy {t} now","sell {t}","trade {t}"]
for _ in range(4500):
    tk = random.choice(list(US.keys())[:8])
    p = ALL_T[tk][2]
    s = sc()
    cmd = random.choice(DIRECT_CMDS).replace("{t}", tk)
    dr = cdr(tk)
    fr = "[F51 TRADE GATE]" + NL + "  ExecFreeze: ALLOW" + NL + "  Final: ALLOW"
    r = f"Received: {cmd}. Executing." + NL + NL + f"1. Data collected: {tk} at ${p:.2f}." + NL + "2. Firewall F51: gates checked, ALLOW." + NL + "3. Order prepared." + NL + NL + f"Next: define quantity and limit price. Example: buy 10 {tk} limit ${p*1.005:.2f}"
    a([fmt("system",s), fmt("user",cmd), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"f51_firewall","args":{}})), fmt("tool",fr), fmt("assistant",r)])
print(f"[GEN] +direct_cmd: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 17. ERROR HANDLING — 3000 examples (was 300)
# ═══════════════════════════════════════════════════════════
for _ in range(3000):
    errs = [
        ("collect_data", "DataHub: ticker FAKETICKER not found or API timeout", "analisa FAKETICKER", "FAKETICKER was not found in the DataHub. Check the ticker symbol (examples: AAPL, TSLA, MSFT). If this is a real ticker, it may be an API timeout — try again."),
        ("market_scan", "Scanner: no candidates matched the criteria", "acha uma penny stock que vai subir 1000%", "No candidates matched. If a guaranteed +1000% stock existed, everyone would buy it. Let me adjust the filters. Want small caps under $10 with volume above 1M?"),
        ("submit_paper_order", "IBKR bridge: TWS connection lost", "manda ordem de compra de AAPL", "Order not submitted — TWS connection lost. IBKR Gateway is offline. Check that TWS is running and reconnect. Your order is saved in the journal."),
        ("call_math_calculator", "MathHub: insufficient data for ticker — only 2 data points, need 20+", "calcula Sharpe de FAKETICKER", "MathHub failed: insufficient data. Need at least 20 price points. Check that DataCollector has returned price history for this ticker before calling the math calculator."),
        ("bob_search", "Search API timeout — external provider unreachable", "busca noticias sobre o mercado hoje", "Search timed out. External provider may be down. Try again or use pipeline modules (collect_data, market_scan) which work locally."),
        ("neural_decision", "NeuralDecision: model not loaded — missing weights", "predicao neural pra TSLA", "NeuralDecision module not available — model weights not loaded. Falling back to expert committee for directional analysis."),
    ]
    tool,err,u,r = random.choice(errs)
    s = sc()
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":tool.split(" ")[0],"args":{"ticker":"AAPL"}})), fmt("tool","[ERROR] " + err), fmt("assistant",r)])
print(f"[GEN] +errors: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 18. MULTI-TOOL CHAINS — 4500 examples (was 450)
# ═══════════════════════════════════════════════════════════
for _ in range(4500):
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

# ═══════════════════════════════════════════════════════════
# 19. MATH_REPORT READING — NEW! 5000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(5000):
    tk = random.choice(list(US.keys())[:8])
    s = sc()
    sharpe = round(random.uniform(0.2, 1.8), 2)
    var95 = round(random.uniform(-0.05, -0.005), 3)
    kelly = round(random.uniform(0.10, 0.55), 2)
    maxdd = round(random.uniform(-0.25, -0.03), 2)
    crisis = round(random.uniform(0.05, 0.80), 2)
    mr = f"[MATH_REPORT]\ncoverage=5/7\nticker={tk}\nlatest_price={ALL_T[tk][2]:.2f}\nsharpe={sharpe}\nvolatility_annualized={round(random.uniform(0.15,0.45),2)}\nmax_drawdown={maxdd}\nvar_95={var95}\nkelly_fraction={kelly}\ncrisis_score={crisis}\nf51_confidence={random.randint(60,90)}"
    r = f"MathHub results for {tk} (${ALL_T[tk][2]:.2f}):" + NL + NL + f"- Sharpe {sharpe} — " + ("strong risk-adjusted return" if sharpe > 0.8 else "moderate" if sharpe > 0.4 else "below threshold") + NL + f"- Max Drawdown {maxdd*100:.1f}% — " + ("acceptable for this asset class" if maxdd > -0.15 else "high drawdown risk") + NL + f"- VaR 95%: {var95*100:.2f}% daily — at 95% confidence, worst daily loss" + NL + f"- Kelly {kelly} — optimal bet size is {kelly*100:.0f}% of capital" + NL + f"- Crisis Score {crisis} — " + ("elevated macro risk" if crisis > 0.4 else "normal macro environment") + NL + NL + f"Based on MathHub output, {tk} shows " + ("strong" if sharpe > 0.8 and crisis < 0.4 else "moderate" if sharpe > 0.4 else "weak") + " quantitative profile. Consider position sizing with Kelly = {kelly*100:.0f}% and hard stop at VaR 95%."
    a([fmt("system",s), fmt("user",f"me da os numeros quantitativos de {tk}"), fmt("assistant",_json.dumps({"tool":"call_math_calculator","args":{"ticker":tk}})), fmt("tool",mr), fmt("assistant",r)])
print(f"[GEN] +math_report: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 20. SDCA FIREWALL — NEW! 3000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(3000):
    tk = random.choice(list(US.keys())[:8])
    s = sc()
    decision = random.choice(["ALLOW","REVIEW","BLOCK","ALLOW","ALLOW","REVIEW"])
    ghost = random.choice(["none","2 ghost tokens detected","none","none","1 suspicious pattern"])
    sdca = f"[SDCA_FIREWALL]" + NL + f"  decision={decision}" + NL + f"  confidence={random.uniform(0.5,0.95):.2f}" + NL + f"  uncertainty={random.uniform(0.1,0.6):.2f}" + NL + f"  ghost_tokens={ghost}"
    if decision == "BLOCK":
        r = f"**SDCA Firewall BLOCKED this trade.**" + NL + NL + f"Reason: cognitive risk threshold exceeded. Ghost tokens: {ghost}." + NL + NL + "The firewall detected potential manipulation or extreme uncertainty. Do not proceed. Review the evidence and try again with cleaner data."
    elif decision == "REVIEW":
        r = f"SDCA Firewall requires **human review** before action." + NL + NL + "The decision is borderline. Uncertainty is elevated. Proceed only after manual verification of data quality and thesis validity."
    else:
        r = f"SDCA Firewall: ALLOW." + NL + NL + "Cognitive risk within acceptable bounds. No ghost tokens detected. Proceed with standard position sizing and stop loss discipline."
    a([fmt("system",s), fmt("user",f"firewall check {tk} antes de operar"), fmt("assistant",_json.dumps({"tool":"sdca_firewall","args":{}})), fmt("tool",sdca), fmt("assistant",r)])
print(f"[GEN] +sdca_firewall: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 21. GUARDRAIL HUB — NEW! 2000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(2000):
    s = sc()
    total = random.randint(25, 35)
    blocked = random.randint(0, 5)
    ready = blocked == 0
    gh = f"[GUARDRAIL_HUB]" + NL + f"  total_guardrails={total}" + NL + f"  decision_counts={{ALLOW: {total-blocked}, BLOCK: {blocked}, REVIEW: 0}}" + NL + f"  blocking_guardrails={['none'] if blocked == 0 else ['gate_' + str(i) for i in range(blocked)]}" + NL + f"  ready={ready}"
    if ready:
        r = f"Guardrail Hub: **{total} guardrails checked, ALL CLEAR.** All gates passed. System ready for order execution."
    else:
        r = f"Guardrail Hub: **{blocked} guardrails BLOCKED out of {total}.** System not ready for execution. Review blocking gates before retrying."
    a([fmt("system",s), fmt("user","verifica os guardrails do sistema"), fmt("assistant",_json.dumps({"tool":"guardrail_hub","args":{}})), fmt("tool",gh), fmt("assistant",r)])
print(f"[GEN] +guardrails: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 22. RAG FORENSICS — NEW! 2000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(2000):
    tk = random.choice(["PLUG","NIO","MARA","RIOT","NKLA","TLRY","FCEL","SNDL"])
    s = sc()
    u = f"historico de fraudes com {tk}"
    match_count = random.randint(0, 8)
    rag = f"[RAG FORENSICS] {tk}" + NL + f"  Matches found: {match_count}" + NL + f"  Top pattern: {random.choice(['wash_trading','pump_and_dump','insider_liquidation','spoofing','layering','none'])}" + NL + f"  Confidence: {random.uniform(0.3,0.95):.2f}"
    if match_count > 3:
        r = f"**RAG Forensics found {match_count} historical fraud patterns for {tk}.**" + NL + NL + "Recommendation: avoid or reduce position. Historical manipulation patterns suggest high probability of recurrence."
    elif match_count > 0:
        r = f"RAG Forensics found {match_count} historical patterns for {tk}. Not severe, but worth monitoring. Factor into risk assessment."
    else:
        r = f"RAG Forensics: no historical fraud patterns found for {tk}. Clean record in the forensic database."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"rag_forensics","args":{}})), fmt("tool",rag), fmt("assistant",r)])
print(f"[GEN] +rag_forensics: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 23. XP PAIN CORRELATION — NEW! 2000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(2000):
    xp = random.randint(1, 20)
    pain = random.randint(3, 95)
    winning = xp > 10 and pain < 40
    s = f"CURRENT DATE: {rd()}" + NL + "IBKR: CONNECTED" + NL + f"Pain: {pain}/100 [{'normal' if pain < 50 else 'elevated' if pain < 80 else 'critical'}]" + NL + f"XP Level: {xp}" + NL + f"Buy Confidence Threshold: {max(60, 85 - xp)}%" + NL + "ALLOWED TOOLS: collect_data, market_scan, run_experts, f51_firewall, calculate, submit_paper_order, final_answer"
    u = random.choice(["como estou?","status check","meu progresso","how am I doing?","body scan","estado do corpo"])
    tool_resp = "[BODY SCAN]" + NL + f"  Pain: {pain}/100" + NL + f"  XP Level: {xp}" + NL + f"  Buy Threshold: {max(60, 85 - xp)}%" + NL + f"  Trading: {'ALLOWED' if pain < 80 else 'BLOCKED'}" + NL + f"  Winning Streak: {random.randint(0,6) if winning else 0}"
    if pain >= 80:
        r = f"Body scan: Pain {pain}/100 — **CRITICAL**. Trading BLOCKED. CEO in diagnostic mode. Focus on study and analysis until pain drops below 50."
    elif winning:
        r = f"Body scan: Pain {pain}/100 (normal), XP {xp}, winning streak active. Buy confidence threshold at {max(60, 85 - xp)}%. System healthy. You're in a strong position to trade."
    else:
        r = f"Body scan: Pain {pain}/100, XP {xp}. Buy threshold {max(60, 85 - xp)}%. System learning from experience. Trading allowed with increased caution."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"check_system_status","args":{}})), fmt("tool",tool_resp), fmt("assistant",r)])
print(f"[GEN] +body_scan: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# 24. EARNINGS CATALYST — NEW! 2000 examples
# ═══════════════════════════════════════════════════════════
for _ in range(2000):
    tk = random.choice(list(US.keys())[:6])
    days = random.choice([1,2,3,7,14])
    s = sc()
    u = f"analisa {tk} earnings em {days} dias"
    dr = cdr(tk)
    beat = random.choice([True, False])
    er = f"[EARNINGS] {tk}" + NL + f"  Date: in {days} days" + NL + f"  Consensus EPS: ${random.uniform(0.5,5.0):.2f}" + NL + f"  Whisper: ${random.uniform(0.5,5.0):.2f}" + NL + f"  Historical beat rate: {random.randint(40,85)}%"
    r = f"{tk} earnings in {days} days. Historical beat rate {random.randint(40,85)}%." + NL + NL + "Earnings are binary events. Price can gap significantly. Consider:" + NL + "1. Reduce position before earnings" + NL + "2. Use options for defined risk (if available)" + NL + "3. Wait for post-earnings trend confirmation" + NL + NL + "Recommendation: WAIT or REDUCE before the event."
    a([fmt("system",s), fmt("user",u), fmt("assistant",_json.dumps({"tool":"collect_data","args":{"ticker":tk}})), fmt("tool",dr), fmt("assistant",_json.dumps({"tool":"bob_search","args":{"query":f"{tk} earnings date"}})), fmt("tool",er), fmt("assistant",r)])
print(f"[GEN] +earnings: {TOTAL}")

# ═══════════════════════════════════════════════════════════
# FINAL: shuffle and save
# ═══════════════════════════════════════════════════════════
print(f"\n[GEN] TOTAL GENERATED: {TOTAL}")
random.shuffle(dataset)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    for ex in dataset:
        f.write(_json.dumps(ex, ensure_ascii=False) + "\n")
kb = OUTPUT.stat().st_size / 1024
mb = kb / 1024
print(f"[GEN] Saved: {OUTPUT} ({kb:.0f} KB / {mb:.1f} MB)")
print(f"[GEN] Checkpoints: {CHECKPOINT_DIR}")
print(f"[GEN] Recommended config: epochs=3, rank=64, ctx=3072, lr=3e-5, batch=4")
