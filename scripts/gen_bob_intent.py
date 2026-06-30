"""Intent Classification Dataset — 1000 examples for Bob to learn intent classification."""
import json, random
from pathlib import Path

random.seed(42)
OUT = Path("temp_gguf_workspace/train_bob_intent.jsonl")
NL = "\n"

def fmt(r,c): return "<|im_start|>"+r+NL+c+"<|im_end|>"
def rd(): return "2026-06-30 10:00 UTC"

dataset = []

# Intent types with examples
INTENTS = {
    "self_check": [
        "como voce esta bob", "faz um body scan", "status check", "verifica o sistema",
        "como estamos", "diagnostico completo", "me mostra teus numeros", "sistema operacional?",
        "check yourself", "how are you doing", "body status", "qual teu estado",
        "tudo bem com voce", "verifica tudo bob", "how is the system", "health check",
        "me da o status completo", "check system", "como ta o corpo", "ta tudo bem ai",
    ],
    "ticker_analysis": [
        "analisa AAPL", "me fala sobre TSLA", "what about NVDA", "devo comprar MSFT",
        "should I buy GOOGL", "how is META doing", "o que acha de AMZN", "tell me about JPM",
        "analisa VALE3", "me explica PETR4", "ITUB4 analise", "analise tecnica de AMD",
        "fundamental analysis INTC", "whats your take on BA", "me da um resumo de DIS",
        "vale a pena NKE", "analise rapida de PYPL", "quick look at COST",
        "o que esperar de JNJ", "analise completa de XOM",
    ],
    "market_scan": [
        "acha penny stock", "scan small caps", "find opportunities", "caca promocao",
        "scan momentum plays", "find undervalued tech", "busca small caps baratas",
        "scan energy sector", "ache crypto mining stocks", "scan Canadian dividend stocks",
        "busca empresas caindo muito hoje", "find oversold stocks", "scan biotech under $5",
        "caca small caps com volume", "find short squeeze candidates",
        "ache growth stocks baratas", "scan REITs with high yield",
        "acha penny stocks de tecnologia com volume anormal",
    ],
    "trade_execution": [
        "compra 10 AAPL limit 280", "vende 50 TSLA", "manda ordem NVDA",
        "buy 20 MSFT limit 480", "sell 100 PLUG", "executa compra de AMZN",
        "quero comprar 5 GOOGL a mercado", "faz um trade de META",
        "ordem paper: compra 25 V limit 350", "submete ordem de venda de DIS",
        "entra comprado em JPM", "fecha posicao de PYPL",
        "compra 1000 acoes de NIO", "vende tudo de MARA",
    ],
    "capital_allocation": [
        "tenho 50k CAD como investir", "herdei 100 mil dolares o que faco",
        "como alocar 25k entre ETFs", "planejamento de aposentadoria 20 anos",
        "quero comprar um imovel ou investir", "divida vs investimento",
        "tenho 10k e 2 filhos pequenos", "portfolio para renda passiva",
        "I have 30k USD to invest for 5 years", "asset allocation 60/40",
        "como diversificar 100k", "estrategia de investimento longo prazo",
        "reserva de emergencia + ETF", "onde colocar 15k por 3 anos",
    ],
    "fraud_check": [
        "vi PLUG bombando no Reddit devo comprar", "NIO é pump and dump?",
        "verifica se MARA tem fraude", "TLRY tem manipulacao?",
        "checa SNDL no RAG", "FCEL é seguro?", "o que o RAG diz sobre RIOT",
        "historico de fraudes de NKLA", "AMC é manipulado?",
        "verifica social forensics de GME", "checa se CLSK tem wash trading",
    ],
    "web_research": [
        "qual o sentimento do mercado hoje", "o que o Reddit acha de NVDA",
        "busca noticias sobre Tesla", "pesquisa sobre earnings da Apple",
        "whats the market saying about crypto", "sentimento sobre small caps",
        "busca no Twitter sobre AMD", "analyst sentiment MSFT this week",
        "social media buzz around AI stocks", "macro context for tech sector",
        "whats trending on Reddit investing", "market sentiment energy sector",
    ],
    "general_question": [
        "oi bob", "bom dia", "ola", "hello", "hey", "quem é voce",
        "o que voce faz", "me explica seu sistema", "como funciona o F51",
        "qual seu proposito", "voce é real", "quem te criou",
        "o que é um ETF", "me explica P/L", "como investir para iniciantes",
        "what is a stop loss", "explain dollar cost averaging",
    ],
}

TOTAL = 0
for intent, questions in INTENTS.items():
    for q in questions:
        s = fmt("system", f"CURRENT DATE: {rd()}\nClassify the user's intent. Respond with ONLY: intent=<type> [ticker=<SYMBOL>]")
        u = fmt("user", q)
        ticker_hint = ""
        for t in ["AAPL","MSFT","NVDA","TSLA","GOOGL","AMZN","META","JPM","JNJ","V","XOM","WMT","COST","AMD","INTC","BA","DIS","NKE","PYPL","PLUG","NIO","MARA","RIOT","TLRY","SNDL","FCEL","NKLA","CLSK","GME","AMC","VALE3","PETR4","ITUB4"]:
            if t in q.upper():
                ticker_hint = f" ticker={t}"
                break
        a = fmt("assistant", f"intent={intent}{ticker_hint}")
        dataset.append({"text": NL.join([s,u,a])})
        TOTAL += 1

# Shuffle and save
random.shuffle(dataset)
OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    for ex in dataset:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"Intent dataset: {TOTAL} examples written to {OUT}")
for intent in INTENTS:
    print(f"  {intent}: {len(INTENTS[intent])} examples")
