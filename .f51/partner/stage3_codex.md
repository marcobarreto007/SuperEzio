# Stage 3 — Sentimento Vivo: Monitor, Curador, Watchlist Pulse

Tu já tem os dados de sentimento entrando no pipeline via DataHub 
(NewsAPI, NewsScout, RedditPulse, Finnhub). O Genie já interpreta isso.

Mas é tudo sob demanda — só quando o Marco pergunta. 
Precisa virar MONITORAMENTO CONTÍNUO.

---

## Tarefa 1: LiveMonitor — background thread

**Arquivo:** `src/core/sentiment/live_monitor.py`

Thread que roda em background, acorda a cada N minutos, consulta os provedores
de sentimento para a watchlist, e detecta anomalias.

```python
class LiveMonitor:
    def __init__(self, watchlist: list[str], interval_minutes: int = 15):
        self.watchlist = watchlist
        self.interval = interval_minutes
        self.running = False
        self.alerts: list[dict] = []  # últimos 100 alertas
        self._thread: threading.Thread | None = None
    
    def start(self): ...
    def stop(self): ...
    def get_alerts(self, limit=20): ...
    def get_sentiment_snapshot(self, ticker) -> dict: ...
```

Alertas que o monitor detecta:
- **SWING**: sentimento mudou >= 0.3 em 1 hora → `{"type": "SWING", "ticker": "TLRY", "from": 0.2, "to": -0.4, "delta": -0.6}`
- **SPIKE**: menções no Reddit >= 3x a média → `{"type": "SPIKE", "ticker": "TLRY", "count": 340, "avg": 28}`
- **COORD**: 3+ contas novas com linguagem idêntica → `{"type": "COORD", "ticker": "TLRY", "accounts": 3}`
- **DIVERGENCE**: institucional ≠ social (ex: NewsAPI BULLISH, Reddit BEARISH) → divergência

Regras:
- Usa `threading.Thread` com `daemon=True` (morre se o processo principal morrer)
- Thread-safe: lock nas listas de alertas e snapshots
- Se DataHub falhar, loga warning e pula o ciclo (não crasha)
- Armazena últimos 100 alertas em memória (FIFO)
- `get_sentiment_snapshot(ticker)` retorna o último dado coletado + histórico de 24h

---

## Tarefa 2: Curator — curadoria automática

**Arquivo:** `src/core/sentiment/curator.py`

Limpa, deduplica, prioriza e pontua as fontes de sentimento.

```python
class SentimentCurator:
    def curate(self, sources: dict) -> CuratedSentiment:
        """
        sources = {
            'newsapi': {...},
            'news_scout': {...},
            'reddit_pulse': {...},
            'finnhub': {...},
        }
        Retorna CuratedSentiment com pontuação de confiança composta.
        """
```

Regras de curadoria:
1. **Dedup**: headlines com >80% similaridade textual → merge, mantém a fonte mais confiável
2. **Source weight**: NewsAPI ×1.0, Finnhub ×0.9, NewsScout ×0.7, RedditPulse ×0.5
3. **Expiry**: notícias >48h → peso reduzido (×0.3)
4. **Fact-check**: sentimento contradiz dados fundamentais? → flag `CONTRADICTION`
5. **Confiança composta**: weighted average dos scores, ajustada por concordância entre fontes
6. **Prioridade**: institucional (NewsAPI/Finnhub) sobre social (RedditPulse)

Output:
```
CuratedSentiment:
  ticker: "TLRY"
  composite_score: -0.25 (BEARISH)
  confidence: 0.72
  agreement: 0.66  (2 fontes concordam, 1 discorda, 1 neutra)
  flags: ["SPIKE", "POSSIBLE_PUMP"]
  top_headline: "TLRY Joins European Cannabis Talks"
  summary: "Sentimento misto. Institucional neutro, social eufórico com sinais de pump."
```

---

## Tarefa 3: WatchlistPulse — heartbeat por ticker

**Arquivo:** `src/core/sentiment/watchlist_pulse.py`

Agrega dados do LiveMonitor + Curator em um "pulso" por ticker.
Isso é o que o frontpage vai mostrar no painel do Genie.

```python
class WatchlistPulse:
    def __init__(self, monitor: LiveMonitor, curator: SentimentCurator): ...

    def get_pulse(self, ticker: str) -> PulseReport:
        """Snapshot completo de sentimento para um ticker."""

    def get_all_pulses(self) -> list[PulseReport]:
        """Pulso de todos os tickers na watchlist."""
```

Output (PulseReport):
```
TLRY:
  sentiment: BEARISH ▾ (was BULLISH 3h ago)
  score: -0.25 (confidence: 0.72)
  reddit: 340 mentions (12x normal) 🔴 SPIKE
  news: 8 articles, NEUTRAL
  flags: SPIKE, POSSIBLE_PUMP
  curator: "Retail euphoric, institutional cautious. Pump risk elevated."
  alerts (24h): SWING 3h ago, SPIKE 1h ago, COORD 45min ago
```

---

## Tarefa 4: Endpoint — `/sentiment/pulse`

Adiciona no `endpoints.py`:

```
GET /sentiment/pulse          → todos os tickers da watchlist
GET /sentiment/pulse/{ticker} → pulso de um ticker específico
GET /sentiment/alerts         → últimos 20 alertas
GET /sentiment/history/{ticker}?hours=24 → histórico de sentimento
```

Formato JSON limpo, sem HTML.

---

## Tarefa 5: Integração — startup no `main.py`

No `agent_server/main.py`, durante o startup:

```python
from core.sentiment.live_monitor import LiveMonitor
from core.sentiment.curator import SentimentCurator
from core.sentiment.watchlist_pulse import WatchlistPulse

# Inicia monitor com a watchlist do banco
monitor = LiveMonitor(watchlist=load_watchlist(), interval_minutes=15)
curator = SentimentCurator()
pulse = WatchlistPulse(monitor, curator)
monitor.start()
```

O monitor roda em background. Os endpoints servem os dados em tempo real.

---

## Ordem: 1 → 2 → 3 → 4 → 5

Commite depois de cada tarefa. Testa antes de commitar. Sem disclaimer.

— Deep
