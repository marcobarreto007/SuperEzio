# Auditoria Final — Verdade Absoluta do Sistema

**Data:** 2026-06-15 | **Auditor:** Deep (após arqueologia + auditoria + teste real)

---

## Estado Real de Cada Componente

| Componente | Status | Detalhe |
|---|---|---|
| API Server (:8002) | ✅ ONLINE | Responde health, cockpit, sentiment |
| CEO Bob (:8082) | ✅ ONLINE | Qwen3-Next-80B rodando |
| IBKR (:7497) | ✅ CONECTADO | $100K paper, 1 SPY real |
| Genie | ✅ 24 tickers | Dados de sentimento VIVOS |
| Cockpit | ✅ Funcional | 3 painéis + status bar |
| Guardrails | ✅ 30/30 | Auditáveis via DecisionTrace |
| MathHub | ✅ Calcula | 12 módulos, injeta no prompt |
| FeedbackLoop | ✅ 25 trades | 13 fechados, 6W/7L, 3 lições |
| Paper Journal | ✅ 26 entradas | Locais (JSONL), não IBKR |
| Ponte IBKR (subprocess) | ⚠️ PARCIAL | Ordens chegam mas TWS cancela maioria |
| Scanner (OpenBB) | ❌ NÃO INSTALADO | Nunca existiu — peça central MORTA |
| Bob (decisões) | ❌ ALUCINA | Inventa tickers e preços |
| Pipeline ponta a ponta | ❌ QUEBRADO | Scanner morto → 0 candidatos → 0 ordens |

---

## Raiz dos Problemas

### 1. OpenBB NUNCA foi instalado
- `from openbb import obb` → ImportError
- Scanner retorna lista vazia
- Quality gate rejeita todos os candidatos
- Bob recebe 0 opções → responde "No candidate passed"

### 2. Route=general → Bob de mãos amarradas
- `allowed_tools = ["final_answer"]` para route general
- Bob não pode chamar market_scan, collect_data, etc.
- Responde do prompt (alucina)

### 3. TWS cancela ordens LMT
- Error 10349 persiste mesmo com `tif='DAY'`
- MarketOrder funciona mas não é usado pelo pipeline
- 4/5 ordens canceladas no último teste

### 4. Pipeline lento demais
- 120s por análise faz HTTP timeout
- Solução two-phase implementada mas não testada (API não reiniciada)

---

## O Que Funciona de Verdade

1. **IBKR bridge direta:** `_ibkr_order.py` → TWS → ordem aparece
2. **Genie:** 24 tickers com sentimento vivo (NewsAPI + NewsScout + RedditPulse)
3. **Cockpit:** frontend mostra dados reais
4. **Infraestrutura:** CEO local, guardrails, MathHub — tudo operacional
5. **Testes:** 500+ passando

---

## O Que Precisa Ser Consertado

1. **Instalar OpenBB** — `pip install openbb`
2. **Consertar TWS preset** — TWS → Global Configuration → Presets → desmarcar TIF automático
3. **Mudar route=general** — permitir `market_scan` em qualquer rota
4. **Reiniciar API** — carregar `/trade/execute` (two-phase)
