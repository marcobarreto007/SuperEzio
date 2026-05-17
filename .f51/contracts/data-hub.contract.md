# DataHub Contract

**Module:** `src/data/data_hub.py`
**Classification:** core

## Public API

### DataHub class

| Method | Signature | Returns | Contract |
|--------|-----------|---------|----------|
| `get_price` | `(symbol: str) -> Dict[str, Any]` | `{"price": float, "source": str, ...}` | Sempre retorna dict. Se provider falhar, tenta fallback. |
| `get_profile` | `(symbol: str) -> Dict[str, Any]` | `{"sector": str, "market_cap": float, ...}` | Sempre retorna dict. |
| `collect_full_mesh` | `(symbol: str) -> Dict[str, Any]` | `{"price": {...}, "fundamentals": {...}, "technicals": {...}, "sentiment": {...}, "social": {...}, "macro": {...}}` | Mesh completo com status por fonte. |
| `get_technicals` | `(symbol: str) -> Dict[str, Any]` | `{"rsi": float, "macd": float, "sma": float, ...}` | Dados técnicos calculados. |

### Provider Registry

Providers registrados no hub:
- `twelve_data` — preço e dados fundamentais
- `alpha_vantage` — preço e dados fundamentais (fallback)
- `newsapi` — sentimento de notícias
- `news_scout` — busca de notícias
- `reddit_pulse` — sentimento social
- `wolfram` — dados quantitativos
- `fed_provider` — dados macro US (FRED/yfinance)
- `boc_provider` — dados macro CA (BOC)

### ProfessionalCollector

O hub expõe `ProfessionalCollector` como fachada de alto nível que orquestra múltiplos providers com circuit breaker e métricas de health.

## Invariants

1. `get_price` nunca levanta exceção — retorna dict com chave de erro em caso de falha.
2. `collect_full_mesh` sempre retorna todas as 6 categorias (price, fundamentals, technicals, sentiment, social, macro), cada uma com status "collected" ou "error".
3. Circuit breaker por provider: 3 falhas consecutivas = circuito aberto.
4. Timeout por provider: 30s default.

## Dependencies

- `.env` — API keys para providers
- Providers individuais em `src/data/` (twelve_data.py, alpha_vantage.py, etc.)
- Pode fazer chamadas de rede para APIs externas
