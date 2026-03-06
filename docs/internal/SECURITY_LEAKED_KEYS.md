# Chaves vazadas no histórico do git — release v3.0.1

Auditoria realizada em 2026-05-12. Resultado de `git log --all -p -S` em prefixos das chaves do `.env` atual.

## Status atual

- `.env` está em `.gitignore` (linhas 56-58 do `.gitignore`).
- `.env.example` documenta as variáveis sem valores.
- Nenhuma chave atual está no working tree de forma versionada — só em `.env` ignorado.

## Chaves que vazaram no histórico (precisam rotacionar)

| Provedor | Commit que introduziu | Onde vazou |
|---|---|---|
| DeepSeek | `9ebb646` | `scripts/update_key.py` (corrigido depois) |
| TwelveData | `a498001` | `src/data/twelve_data.py` |
| Alpha Vantage | `a498001` | `src/data/alpha_vantage.py` |
| NewsAPI | `a498001` | `src/data/news_feed.py` |

## Chaves limpas na auditoria local (sem hits no histórico)

- HuggingFace
- Wolfram
- CoinGecko
- The Odds API

## Decisão necessária antes da entrega

Duas opções, mutuamente exclusivas:

### Opção A — Rotacionar (recomendado)

1. Revogar as 4 chaves vazadas no painel de cada provedor (DeepSeek, TwelveData, Alpha Vantage, NewsAPI).
2. Gerar chaves novas e atualizar `.env` local.
3. Repo com histórico atual pode ser entregue ao cliente; as chaves antigas no histórico viram inúteis.

**Custo**: minutos. **Risco**: zero (se feito antes da entrega).

### Opção B — Reescrever histórico (destrutivo)

1. `git filter-repo --replace-text` ou BFG para apagar os blobs com chaves.
2. `git push --force-with-lease` em todas as branches.
3. Quem tiver clone precisa re-clonar.

**Custo**: alto (coordenação). **Risco**: alto (perder commits, forks ficarem órfãos). **Recomendar apenas se o cliente exigir histórico limpo.**

## Não fazer

- ❌ Entregar o repo sem rotacionar as 4 chaves.
- ❌ Usar `git filter-branch` (deprecado, lento, problemático com Windows).
- ❌ Re-commitar `.env` para "limpar" — `.env` continua ignorado, isso não muda nada no histórico.
