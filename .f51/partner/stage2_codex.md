# Stage 2 — Trindade: Bob ↔ Genie ↔ Deep (Diálogo Bidirecional)

Tu tá construindo um conselho de administração. O Bob (CEO, Qwen local) dialoga 
com dois conselheiros: Genie (Gemini, sentimento/informação) e Deep (DeepSeek, matemática).

Hoje é fire-and-forget: cada expert responde uma vez e o Bob lê.

Precisa virar DIÁLOGO: Bob pergunta → expert responde → Bob faz follow-up → expert refina.

---

## Tarefa 1: `MathPrompt` — números estruturados pro DeepSeek

**Arquivo:** `src/core/pipeline/prompts/math_prompt.py`

O `MathHub.to_deepseek_prompt()` já existe e gera `[MATH_REPORT]`. 
Mas o formato atual é muito verboso (especialmente a crise com 12 modelos).

Cria um formatador que gere:

```
[MATH_CONTEXT]
Ticker: AAPL | Price: $215.30
Returns: annualized=-1.1% | volatility=2.9% | Sharpe=-39.2
Risk: VaR_95=-$0.67 | max_drawdown=-3.9% | Kelly=N/A
Crisis: regime=NORMAL | score=20/100 (low risk)
Technicals: RSI=N/A, MACD=N/A, VWAP=$210.96
[/MATH_CONTEXT]
```

Regras:
- Máximo 8 linhas. Sem JSON dentro do prompt. 
- Se valor é None, escreve "N/A".
- Se módulo foi skipped, omite ou escreve "skipped".
- A crise só mostra `regime` e `aggregate_score` (não os 12 modelos individuais).
- Usa 2 casas decimais pra preço, 1 pra percentuais.

---

## Tarefa 2: `SentimentPrompt` — dados estruturados pro Genie

**Arquivo:** `src/core/pipeline/prompts/sentiment_prompt.py`

O Genie (Gemini) recebe os dados de sentimento do DataHub. 
Hoje recebe `data_context` como texto bruto.

Cria um formatador que gere:

```
[SENTIMENT_CONTEXT]
Ticker: TLRY
NewsAPI: 8 artigos | sentimento BULLISH (+0.3) | "TLRY Joins European Cannabis Talks"
NewsScout: 12 artigos | sentimento NEUTRAL (0.0)
RedditPulse: 340 menções (SPIKE 12x normal) | 5 posts qualificados | 3 contas suspeitas
Finnhub: 3 company announcements | sentimento NEUTRAL
CURATOR: 2 fontes concordam (BULLISH) | 1 fonte discorda | confiança composta=0.65
[/SENTIMENT_CONTEXT]
```

Regras:
- Extrai do state: `data.sentiment`, `data.reddit`, `data.news`, `data.finnhub_news`
- Se fonte não existe, omite a linha.
- Se `sentiment_label == "NO_DATA"`, escreve "sem dados".
- Reddit: mostra `qualified_count`, `signal_label`, e `top_posts[0].title` se existir.
- Curator (se existir): mostra concordância/discordância entre fontes.

---

## Tarefa 3: `ExpertDialogue` — multi-turn com follow-up

**Arquivo:** `src/core/pipeline/nodes/expert_dialogue.py`

Refatora `node_expert()` para suportar múltiplos rounds de diálogo.

```python
class ExpertDialogue:
    def __init__(self, gateway, max_rounds=3):
        self.gateway = gateway
        self.max_rounds = max_rounds
        self.history: list[dict] = []  # cada round
    
    async def ask(self, role, provider, system_prompt, user_prompt):
        """Primeira pergunta — fire and forget original."""
        ...
    
    async def follow_up(self, role, provider, question):
        """Bob faz follow-up. History dos rounds anteriores é incluída."""
        ...
    
    def get_verdict(self) -> dict:
        """Extrai o veredito final + confiança do último round."""
        ...
```

Fluxo:
1. Bob recebe MathReport + SentimentReport
2. Bob chama `dialogue.ask("fundamental_value", "deepseek", system, prompt_com_numeros)`
3. Deep responde com veredito + reasoning
4. Bob lê, decide se precisa de follow-up
5. Se sim: `dialogue.follow_up("fundamental_value", "deepseek", "Mas e o DCF? O fair value tá 8% abaixo. Isso não te preocupa?")`
6. Deep refina resposta com o novo contexto
7. Máximo 3 rounds

---

## Tarefa 4: `TrinityNode` — orquestrador dos 3

**Arquivo:** `src/core/pipeline/nodes/trinity.py`

O nó que o pipeline chama depois do `auto_full_analysis`:

```python
async def node_trinity(state, *, gateway=None):
    """
    1. MathHub → MathPrompt (números pro Deep)
    2. SentimentPrompt → SentimentContext (dados pro Genie)
    3. Para cada expert: ExpertDialogue (multi-turn)
    4. Coleta vereditos + raciocínios
    5. Formata TrinityReport pro Bob
    """
```

Output: `trinity_report` com:

```
=== TRINITY DELIBERATION ===

GENIE (sentiment):
  Round 1: SUSPICIOUS (72) — "Reddit spike com 3 contas novas. Pump risk."
  Round 2: "Confirmado — as 3 contas postaram texto idêntico em r/pennystocks."

DEEP (fundamental):
  Round 1: OVERVALUED (68) — "DCF $1.10 vs market $1.85. Sem catalisador."
  Round 2: "Mesmo com growth +5%, DCF só vai a $1.40. Ainda abaixo."

CONSENSUS: Ambos negativos. Sem divergência.
BOB DECISION: WAIT (78). Genie + Deep alinhados.
OVERRIDE: Nenhum.

=== END TRINITY ===
```

---

## Tarefa 5: Integração no `graph.py`

Adiciona `node_trinity` no pipeline:

```python
# Depois do auto_full_analysis, ANTES do agent (Bob)
builder.add_node("trinity", _trinity)
builder.add_edge("auto_full_analysis", "trinity")
builder.add_conditional_edges(
    "trinity",
    route_after_trinity,
    {
        "agent": "agent",
        "respond_blocked": "respond_blocked",
    },
)
```

O `route_after_trinity` verifica: se trinity_report indica BLOCK unânime → pula Bob → explanation direto.

---

## Ordem de implementação:

1. `math_prompt.py` — o mais simples, só formatar
2. `sentiment_prompt.py` — extrair do state
3. `expert_dialogue.py` — o core, multi-turn
4. `trinity.py` — orquestrador
5. Integrar no `graph.py`

Faz uma tarefa por vez. Commita depois de cada uma. Testa antes de commitar.

— Deep
