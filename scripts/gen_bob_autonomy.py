"""Bob Autonomy Dataset Generator — 30K total (10K finance + 20K autonomy).
Run: python scripts/gen_bob_autonomy.py
Output: temp_gguf_workspace/train_bob_autonomy.jsonl (~30K examples, ~15 MB)
"""
import json, random, os
from pathlib import Path
from datetime import datetime, timedelta

random.seed(42)
OUT = Path("temp_gguf_workspace/train_bob_autonomy.jsonl")
NL = "\n"

US = {k:(n,s,p) for k,n,s,p in [
    ("AAPL","Apple Inc","Technology",283.78),("MSFT","Microsoft Corp","Technology",478.52),
    ("NVDA","NVIDIA Corp","Technology",142.10),("GOOGL","Alphabet Inc","Technology",198.35),
    ("AMZN","Amazon.com Inc","Consumer",232.80),("META","Meta Platforms","Technology",635.00),
    ("TSLA","Tesla Inc","Automotive",385.20),("JPM","JPMorgan Chase","Financial",268.15),
    ("JNJ","Johnson & Johnson","Healthcare",172.40),("V","Visa Inc","Financial",352.80),
    ("XOM","Exxon Mobil","Energy",119.30),("WMT","Walmart Inc","Consumer",95.60),
    ("COST","Costco Wholesale","Consumer",1045.00),("AMD","AMD","Technology",165.30),
    ("INTC","Intel Corp","Technology",21.45),("BA","Boeing Co","Industrial",175.20),
]}

def fmt(r,c): return "<|im_start|>"+r+NL+c+"<|im_end|>"
def rd(): return (datetime(2026,1,1)+timedelta(days=random.randint(0,364))).strftime("%Y-%m-%d %H:%M UTC")
def sc(): return "CURRENT DATE: "+rd()+NL+"IBKR: CONNECTED | Paper: $10000"+NL+"Pain: 5/100 [normal]"+NL+"ALLOWED TOOLS: bob_search, rag_forensics, collect_data, market_scan, run_experts, f51_firewall, calculate, submit_paper_order, check_system_status, final_answer"
def cdr(tk): n,s,p=US.get(tk,(tk,"Unknown",100.0)); return f"[{tk}] {n}. ${p:.2f}. Sector: {s}. RSI(14): {random.choice([35,48,55,62,68])}. MACD: {random.choice(['bullish crossover','bearish crossover'])}."

dataset = []; TOTAL = 0
def a(msgs):
    global TOTAL; dataset.append({"text": NL.join(msgs)}); TOTAL += 1
    if TOTAL % 5000 == 0: print(f"  [CKPT] {TOTAL} examples...")

def demo_sys(): return fmt("system",sc())

# ═══════════════════════════════════════════════════════════════
# PART 1: FINANCE 10K — extended market knowledge
# ═══════════════════════════════════════════════════════════════
print("[1/4] Finance 10K...")

# 1a. Ticker analysis with full pipeline (4K)
for _ in range(4000):
    tk = random.choice(list(US.keys()))
    s = demo_sys(); u = fmt("user",random.choice([f"analisa {tk}",f"devo investir em {tk}",f"what about {tk}",f"me explica {tk}"]))
    t1 = fmt("assistant",'{"tool":"collect_data","args":{"ticker":"'+tk+'"}}')
    t1r = fmt("tool",cdr(tk))
    t2 = fmt("assistant",'{"tool":"run_experts","args":{}}')
    t2r = fmt("tool","[EXPERT COMMITTEE]\n  fundamental: BULLISH (78%)\n  technical: NEUTRAL (62%)\n  macro: "+random.choice(["BEARISH","NEUTRAL","BULLISH"])+" ("+str(random.randint(50,75))+"%)\n  Consensus: "+random.choice(["MIXED","CAUTIOUSLY_BULLISH","BULLISH"]))
    t3 = fmt("assistant",'{"tool":"f51_firewall","args":{}}')
    t3r = fmt("tool","[F51 TRADE GATE]\n  ExecFreeze: ALLOW\n  TickerValidation: ALLOW\n  Final: ALLOW")
    r = f"## {tk}\n\nData: {cdr(tk)}\nExperts: mixed. Firewall: ALLOW.\nVerdict: {random.choice(['BUY_CANDIDATE','STUDY_MORE','WATCHLIST'])} ({random.randint(65,88)}% conf).\nNext: calculate position + stop loss."
    a([s,u,t1,t1r,t2,t2r,t3,t3r,fmt("assistant",r)])

# 1b. Market scan (2K)
for _ in range(2000):
    s = demo_sys(); u = fmt("user",random.choice(["acha small caps com volume","scan oportunidades tech","busca penny stock barata","find oversold stocks","scan momentum plays"]))
    ks = random.sample(list(US.keys()),min(5,len(US)))
    tr = "[MARKET SCAN]\n"+NL.join(f"  {k}: {US[k][0]} ${US[k][2]:.2f} | {US[k][1]}" for k in ks)
    r = "Scan results:\n"+NL.join(f"**{k}**: {US[k][0]} ${US[k][2]:.2f}" for k in ks[:3])+"\n\nWant deep-dive on any?"
    a([s,u,fmt("assistant",'{"tool":"market_scan","args":{"query":"scan"}}'),fmt("tool",tr),fmt("assistant",r)])

# 1c. Calculate + position sizing (2K)
for _ in range(2000):
    tk = random.choice(list(US.keys())); p = US[tk][2]; cap = random.choice([5000,10000,25000,50000])
    rp,sp = random.choice([0.5,1.0,1.5,2.0]), random.choice([5,8,10,12,15])
    s = demo_sys(); u = fmt("user",f"tamanho posicao {tk}: ${cap}, risco {rp}%, stop {sp}%")
    ra = cap*rp/100; mp = ra/(sp/100); ms = max(1,int(mp/p))
    tr = fmt("tool",f"[CALC] max_risk=${ra:.2f}")
    r = f"Used calculate('position({cap},{rp},{sp})'):\n- Max Risk: ${ra:.2f} ({rp}% of ${cap})\n- Position: ${mp:.2f}\n- Shares of {tk} (at ${p:.2f}): **{ms} shares**\n- Stop: ${p*(1-sp/100):.2f}"
    a([s,u,fmt("assistant",'{"tool":"calculate","args":{"expression":"position('+str(cap)+','+str(rp)+','+str(sp)+')"}}'),tr,fmt("assistant",r)])

# 1d. Paper orders (2K)
for _ in range(2000):
    tk = random.choice(list(US.keys())[:8]); p = US[tk][2]; act = random.choice(["BUY","SELL"])
    qty = random.choice([5,10,20,50,100]); lp = round(p*random.uniform(0.995,1.005),2)
    s = demo_sys(); u = fmt("user",f"compra {qty} {tk} limit ${lp}")
    dr = fmt("tool",cdr(tk))
    fr = fmt("tool","[F51 TRADE GATE]\n  ExecFreeze: ALLOW\n  Final: ALLOW")
    oid = f"PAPER-{random.randint(10000,99999)}"
    or_ = fmt("tool",f"[PAPER ORDER]\n  ID: {oid}\n  {tk} {act} {qty} @ ${lp:.2f} LMT\n  Status: SUBMITTED")
    r = f"Paper order: {tk} {act} {qty} @ ${lp:.2f}\nStop: ${lp*0.92:.2f} (-8%)\nMax risk: ${qty*lp*0.08:.2f}"
    a([s,u,fmt("assistant",'{"tool":"collect_data","args":{"ticker":"'+tk+'"}}'),dr,fmt("assistant",'{"tool":"f51_firewall","args":{}}'),fr,fmt("assistant",'{"tool":"submit_paper_order","args":{"ticker":"'+tk+'","action":"'+act+'","qty":'+str(qty)+',"limit_price":'+str(lp)+'}}'),or_,fmt("assistant",r)])
print(f"  Finance: {TOTAL}")

# ═══════════════════════════════════════════════════════════════
# PART 2: SELF-KNOWLEDGE 5K — Bob checks himself
# ═══════════════════════════════════════════════════════════════
print("[2/4] Self-Knowledge 5K...")

SELF_Q = [
    "como voce esta bob","faz um body scan","status check","how are you doing",
    "verifica o sistema","check yourself","diagnostico completo","me mostra teus numeros",
    "qual teu estado","tudo bem com voce","sistema operacional?","body status",
    "me da o status completo","verifica tudo bob","how is the system",
]
SELF_PAIN_MODES = ["normal","elevated","man_at_work","critical"]
SELF_IBKR_STATES = ["CONNECTED","CONNECTED","CONNECTED","OFFLINE"]

for _ in range(5000):
    s = demo_sys(); u = fmt("user",random.choice(SELF_Q))
    pain = random.choice([5,8,12,25,45,65,78,88,95])
    mode = "critical" if pain>80 else ("man_at_work" if pain>60 else ("elevated" if pain>35 else "normal"))
    ibkr = random.choice(SELF_IBKR_STATES)
    xp = random.randint(1,20)
    tool_resp = "[SYSTEM STATUS]\n  IBKR: "+ibkr+"\n  Portfolio: $10000 paper\n  Pain: "+str(pain)+"/100 ["+mode+"]\n  XP: "+str(xp)+"\n  Guardrails: ALLOW\n  GPU: RTX 5060Ti 16GB"
    
    if mode == "critical":
        r = f"Body scan: **Pain {pain}/100 — CRITICAL**. IBKR: {ibkr}. XP: {xp}. Trading: BLOCKED. I'm in diagnostic mode — zero orders until pain drops below 50. I can still analyze and study."
    elif mode == "man_at_work":
        r = f"Body scan: Pain {pain}/100 — ELEVATED. Mode: man_at_work. CEO diagnostic active. Trading BLOCKED. IBKR: {ibkr}. I can research and prepare, but no orders until recovery."
    elif ibkr == "OFFLINE":
        r = f"Body scan: Pain {pain}/100 (normal). XP: {xp}. IBKR: **OFFLINE** — no trade execution possible. Check TWS/Gateway connection. All other systems nominal."
    else:
        r = f"Body scan: Pain {pain}/100 (normal). IBKR: CONNECTED. XP: {xp}. Portfolio: $10K paper. All guardrails green. System healthy. Ready to operate."
    
    a([s,u,fmt("assistant",'{"tool":"check_system_status","args":{}}'),fmt("tool",tool_resp),fmt("assistant",r)])
print(f"  Self-knowledge: {TOTAL}")

# ═══════════════════════════════════════════════════════════════
# PART 3: RAG + INTERNAL DOCS 5K
# ═══════════════════════════════════════════════════════════════
print("[3/4] RAG Research 5K...")

RAG_TOPICS = {
    "fraud": ["wash trading","pump and dump","spoofing","layering","insider trading","front running","dark pool manipulation","painting the tape","quote stuffing","spoofing patterns"],
    "lessons": ["stop loss ausente","tamanho errado de posicao","FOMO em microcap","entrada sem firewall","venda por panico","alavancagem errada","day trade sem edge","semanal sem catalisador","noticia ignorada","gap nao preenchido"],
    "system": ["F51 Trade Gate","guardrail hub","SDCA firewall","neural decision","MathHub calculator","penny momentum backtest","expert committee roles","trinity deliberation","portfolio HRP weights","crisis aggregate score"],
    "patterns": ["bullish engulfing","head and shoulders","double bottom","RSI divergence","MACD golden cross","Bollinger squeeze","volume spike confirmation","support breakout","resistance test","cup and handle"],
}

for _ in range(5000):
    topic = random.choice(list(RAG_TOPICS.keys()))
    query = random.choice(RAG_TOPICS[topic])
    s = demo_sys(); u = fmt("user",f"Bob, o que voce sabe sobre {query}?")
    
    match_count = random.randint(0,15)
    confidence = random.uniform(0.4,0.95)
    source = random.choice(["paper_journal.jsonl","learning_log.jsonl","rag_forensics","bob_pain_log.jsonl","r/"+random.choice(["stocks","investing","wallstreetbets"])])
    
    tr = f"[RAG SEARCH]\n  Query: {query}\n  Matches: {match_count}\n  Source: {source}\n  Confidence: {confidence:.2f}"
    
    if match_count > 5:
        r = f"RAG search for '{query}': Found **{match_count}** historical patterns. Source: {source}. Confidence: {confidence:.1%}.\n\nKey findings:\n- Pattern detected in {match_count} cases\n- Common characteristics: volume anomaly, coordinated timing\n- Recommendation: factor this into risk assessment.\n\nThis is historical data, not prediction. Current market conditions may differ."
    elif match_count > 0:
        r = f"RAG search for '{query}': Found {match_count} matches in {source}. Low evidence — use with caution. Confidence: {confidence:.1%}."
    else:
        r = f"RAG search for '{query}': No historical patterns found in internal database. This doesn't mean it's safe — it means we haven't seen it before. Treat as unknown risk."
    
    a([s,u,fmt("assistant",'{"tool":"rag_forensics","args":{}}'),fmt("tool",tr),fmt("assistant",r)])
print(f"  RAG: {TOTAL}")

# ═══════════════════════════════════════════════════════════════
# PART 4: WEB SEARCH + SCRAPING 5K
# ═══════════════════════════════════════════════════════════════
print("[4/4] Web Search 5K...")

WEB_QUERIES = [
    "sentimento do mercado sobre {t} hoje",
    "o que o Reddit ta falando de {t}",
    "noticias recentes {t} earnings",
    "whats the market saying about {t}",
    "busca no Twitter sobre {t}",
    "analyst sentiment {t} this week",
    "social media buzz around {t}",
    "{t} news catalysts",
    "insider trading {t} recent",
    "short interest {t} latest",
    "google 'should I buy {t}' e me diz",
    "busca institucional sobre {t}",
    "macro context for {t} sector",
]

for _ in range(5000):
    tk = random.choice(list(US.keys()))
    query = random.choice(WEB_QUERIES).replace("{t}", tk)
    s = demo_sys(); u = fmt("user",query)
    
    sources = random.choice(["Reddit","Twitter/X","Google News","Yahoo Finance","Bloomberg","Reuters","Seeking Alpha","Benzinga"])
    sentiment = random.choice(["positive","negative","neutral","mixed","cautiously bullish","cautiously bearish"])
    posts = random.randint(5,500)
    key_phrase = random.choice(["momentum building","overvalued concerns","earnings beat expected","downgrade risk","upgrade potential","sector rotation","institutional buying","retail frenzy","short squeeze candidate","value play"])
    
    tr = f"[BOB SEARCH]\n  Query: '{query}'\n  Source: {sources} ({posts} posts)\n  Sentiment: {sentiment}\n  Key finding: {key_phrase}"
    
    r = f"Web search for '{query}':\n\n**{sources}**: {posts} posts, overall sentiment **{sentiment}**.\nKey finding: {key_phrase}.\n\n**Note**: Social media sentiment is directional, not predictive. Cross-reference with pipeline data before acting.\n\nWant me to run full pipeline analysis on {tk} now?"
    
    a([s,u,fmt("assistant",'{"tool":"bob_search","args":{"query":"'+query[:60]+'"}}'),fmt("tool",tr),fmt("assistant",r)])
print(f"  Web: {TOTAL}")

# ═══════════════════════════════════════════════════════════════
# PART 5: FULL AUTONOMY PIPELINE 5K
# ═══════════════════════════════════════════════════════════════
print("[5/5] Autonomy Pipeline 5K...")

for _ in range(5000):
    tk = random.choice(list(US.keys())[:6])
    s = demo_sys(); u = fmt("user",f"Bob, quero investir ${random.choice([5000,10000,25000])} em {tk}. Pesquise tudo e me diga se devo comprar.")
    
    # Step 1: Self-check
    msgs = [s,u]
    msgs.append(fmt("assistant",'{"tool":"check_system_status","args":{}}'))
    msgs.append(fmt("tool","[SYSTEM STATUS]\n  IBKR: CONNECTED\n  Pain: 5/100 [normal]\n  XP: 12\n  Guardrails: ALLOW"))
    
    # Step 2: Web research
    msgs.append(fmt("assistant",'{"tool":"bob_search","args":{"query":"'+tk+' analyst sentiment news"}}'))
    msgs.append(fmt("tool",f"[BOB SEARCH]\n  Sources: Seeking Alpha, Yahoo Finance, Reddit\n  Sentiment: cautiously bullish\n  Catalyst: upcoming product launch"))
    
    # Step 3: RAG check
    msgs.append(fmt("assistant",'{"tool":"rag_forensics","args":{}}'))
    msgs.append(fmt("tool",f"[RAG FORENSICS] {tk}\n  Historical patterns: 2\n  Fraud risk: LOW"))
    
    # Step 4: Market data
    msgs.append(fmt("assistant",'{"tool":"collect_data","args":{"ticker":"'+tk+'"}}'))
    msgs.append(fmt("tool",cdr(tk)))
    
    # Step 5: Experts
    msgs.append(fmt("assistant",'{"tool":"run_experts","args":{}}'))
    msgs.append(fmt("tool","[EXPERT COMMITTEE]\n  fundamental: BULLISH (82%)\n  technical: BULLISH (74%)\n  macro: NEUTRAL (58%)\n  Consensus: BULLISH"))
    
    # Step 6: Firewall
    msgs.append(fmt("assistant",'{"tool":"f51_firewall","args":{}}'))
    msgs.append(fmt("tool","[F51 TRADE GATE]\n  All 10 gates: ALLOW"))
    
    # Step 7: Position sizing
    cap = 10000; p = US[tk][2]; rp,sp = 2.0,10.0
    ra = cap*rp/100; mp = ra/(sp/100); ms = max(1,int(mp/p))
    msgs.append(fmt("assistant",'{"tool":"calculate","args":{"expression":"position(10000,2,10)"}}'))
    msgs.append(fmt("tool",f"[CALC] max_risk=${ra:.2f}, shares={ms}"))
    
    # Step 8: Final verdict
    r = f"## {tk} — Full Autonomy Analysis\n\n1. **Self-check**: System healthy, IBKR connected ✅\n2. **Web research**: Sentiment cautiously bullish, product catalyst ✅\n3. **RAG forensics**: 2 historical patterns, low fraud risk ✅\n4. **Market data**: {cdr(tk)}\n5. **Expert committee**: BULLISH consensus (fundamental 82%, technical 74%)\n6. **F51 Firewall**: ALLOW — all 10 gates passed ✅\n7. **Position**: {ms} shares at ${p:.2f} (max risk ${ra:.2f})\n\n**Verdict: BUY_CANDIDATE** — 84% confidence.\nNext: submit_paper_order for {ms} {tk} limit ${p*1.005:.2f}.\nStop: ${p*0.9:.2f} (-10%). Target: ${p*1.2:.2f} (+20%)."
    msgs.append(fmt("assistant",r))
    a(msgs)
print(f"  Autonomy: {TOTAL}")

# ═══════════════════════════════════════════════════════════════
# SAVE
# ═══════════════════════════════════════════════════════════════
random.shuffle(dataset)
OUT.parent.mkdir(parents=True,exist_ok=True)
with open(OUT,"w",encoding="utf-8") as f:
    for ex in dataset: f.write(json.dumps(ex,ensure_ascii=False)+"\n")
mb = OUT.stat().st_size/1024/1024
print(f"\n[DONE] {TOTAL} examples, {mb:.1f} MB → {OUT}")
