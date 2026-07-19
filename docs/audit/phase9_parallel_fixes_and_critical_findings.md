# Fase 9 — Correções paralelas (4 subagentes) + achados críticos de segurança

Gerado: 2026-07-19
Método: 4 subagentes rodando em paralelo, cada um com escopo de arquivo exclusivo (sem conflito),
mais verificação independente de achados críticos reportados por outra sessão de auditoria.

## Correções aplicadas (4 subagentes, todas com commit local + teste de regressão)

### 1. `fix(f51): spider_sense hardcoded evidence + critic fail-open on exception` (`4bda75c`)
- **5.1 spider_sense**: `src/f51/graph.py` fazia `*spider.detect(...)` desempacotando `(danger, alerts)` errado
  no parâmetro `confidence` (deveria ser `float`, recebia uma `list`), e `evidence={"danger": 1.0}` era
  constante. Corrigido: `confidence = clamp(1.0 - danger)`, `evidence` usa o `danger` real.
- **5.4 critic fail-open**: `src/f51/gates.py` retornava `is_valid=True, confidence=0.5` em exceção do
  critique. Corrigido para `is_valid=False, confidence=0.1` — fail-closed, alinhado ao princípio do
  `f51_trade_gate.py` ("fails CLOSED. If in doubt, BLOCK").
- **5.2 proxy de confiança**: usava constante `0.2 * 0.8`; agora usa `veracity_gate.confidence` real.
- **5.3 (thresholds fixos)**: avaliado e deliberadamente NÃO alterado — são constantes de calibração de
  design (`FormulaWeights.default()`, `decision_threshold()`), não bugs; mudá-las é decisão arquitetural
  fora do escopo de correção cirúrgica.
- Testes: 187 → 189 passed (2 novos testes de regressão).

### 2. `fix(data): reject empty dict as usable DataHub result` (`ea63541`)
- **DataHub `{}` aceito como sucesso**: `_is_usable_result` agora exige `len(result) > 0` além de
  `"error" not in result` — dict vazio não quebra mais a cadeia de fallback Finnhub→TwelveData→
  yfinance→Stooq. Dicts com valores falsy mas com chaves (`{"price": 0}`) continuam aceitos corretamente.
- **`exec()` em `custom_tools.py:315`**: investigado a fundo. Já tinha defesa em profundidade não
  documentada (opt-in via `SUPEREZIO_ENABLE_PYTHON_EXEC`, AST allowlist/blocklist bloqueando
  import/dunder/builtins perigosos, `__builtins__` restrito). Testados manualmente 14 payloads clássicos
  de bypass de sandbox — todos bloqueados. Decisão: mantido (não removido), reforçado com 18 novos testes
  de regressão provando que os bypasses continuam bloqueados.
- Testes: 8 → 40 passed (32 novos).

### 3. `fix(mission): expire IBKR apprenticeship status by real date, not static JSON` (`10490cf`)
- O contexto de identidade injetado no prompt do Bob (`src/core/mission_context.py`) afirmava
  `status: "active_training_window"` para um apprenticeship de 14 dias com `end_date: 2026-06-19` —
  já expirado há um mês. Corrigido com checagem de data real (`_resolve_apprenticeship_status`,
  compara `datetime.now()` contra `end_date` parseado) em vez de depender de edição manual do JSON.
  Agora o prompt gerado inclui nota explícita "this training window has ENDED" quando aplicável.
  `config/mission_context.json` (fonte dos dados) não foi editado — a correção é robusta a qualquer
  data futura, não só a esta expiração específica.
- Testes: sem regressão; suíte completa 1373 passed no momento desta correção.

### 4. `fix(experts): red team fallback prompt crashed with KeyError(provider)` (`d8ca01b`)
- **Causa raiz real do `KeyError('provider')`** que fazia todo agente de red team falhar: o prompt
  fallback genérico (usado por roles sem entrada em `EXPERT_PROMPTS`, caso de `red_team_agent_N`) era
  montado como f-string já interpolada, e essa string **já resolvida** era passada de novo por
  `.format(ticker=..., context=...)`. Quando `context` continha chaves literais tipo `{provider}`
  (comuns em texto de outros experts ou repr de dict), `str.format()` procurava esse placeholder
  inexistente e lançava `KeyError`. Corrigido: caminho fallback agora usa a f-string diretamente, sem
  reformatação.
- **SDCA `_truthy_high` tratando "low" como risco alto**: `sdca_lite.py:43` incluía `"low"` num set de
  valores "high-risk" usado para campos como `flow_toxicity`, `leverage`, `spread` — invertendo a
  semântica (leverage="low" disparava alerta de risco alto). Removido `"low"` do set.
- Testes: 63 → 64 passed (1 novo teste de regressão com chaves literais no contexto).

## Verificação consolidada (todos os 4 juntos)

- `git log --oneline`: 4 commits limpos, cada um tocando apenas os arquivos do seu escopo declarado,
  sem sobreposição nem conflito.
- Suíte completa após os 4 merges: **1402 passed, 0 failed, 11 skipped**.
- Teste ao vivo (`analyze SHOP for me`, servidor real rodando): `KeyError('provider')` não ocorre mais
  no red team (agora falha com `strict_json_validation_failed` quando ocorre — um problema diferente e
  legítimo de qualidade de resposta do LLM, não um bug de código); `f51_unified` retorna `status: ok`;
  `fallback_used: false` — resposta real sintetizada.
- Teste ao vivo consumidor (`"I'm new to investing, where should I start?"`): resposta completa, honesta
  sobre o que o produto é ("No broker, no real-money execution here. I'm a financial copilot, not a
  broker"), sem promessa vazia, `fallback_used: false`.

## Achados críticos de segurança (verificados, NÃO corrigidos — pendência do operador)

Reportados por outra sessão de auditoria em paralelo; verifiquei cada um com leitura direta antes de
aceitar ou refutar. **Ambos confirmados como reais**, não refutados:

### CRÍTICO — Token Hugging Face real exposto no repositório
- Confirmado em `F51-Nitro-MoE/dl_mixtral.sh:2` e `F51-Nitro-MoE/download_mixtral.sh:2`
  (`export HF_TOKEN="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"`), além de mais 4 arquivos encontrados nesta
  sessão: `F51-Nitro-MoE/dl_glm2.py`, `dl_mixtral.py`, `dl_glm.py`, `dl2.py`.
- **NÃO CORRIGIDO nesta sessão por instrução explícita do operador ("cara nao toke em tokens")** — uma
  tentativa de correção em `dl_mixtral.sh`/`download_mixtral.sh` foi revertida a pedido antes de
  qualquer commit.
- **Ação pendente, só o operador pode fazer**: revogar/rotacionar o token na conta Hugging Face. Trate
  como comprometido — está versionado no histórico do git, então mesmo removendo do arquivo atual, o
  valor continua recuperável via `git log`/`git show` a menos que o histórico seja reescrito (ação de
  maior risco, decisão separada).

### CRÍTICO — RAG usa `np.load(..., allow_pickle=True)`
- Confirmado em `src/core/rag/engine.py:388`. Pickle deserializa objetos Python arbitrários — se o
  arquivo de índice (`docs_path`) for adulterado por qualquer meio, isso é um vetor de execução de
  código arbitrário no momento de carregar a memória RAG.
- **NÃO CORRIGIDO nesta sessão** (mesma instrução do operador — parar de mexer em qualquer coisa
  relacionada a segredos/segurança sensível até nova instrução explícita). Registrado aqui para ação
  futura: migrar para `allow_pickle=False` ou formato serializado com validação (json, ou pickle restrito
  com allowlist de classes).

### Outros achados relatados (não verificados por mim nesta sessão — reportar com cautela)
A mesma auditoria externa listou vários outros pontos (ALTO/MÉDIO): ausência de autenticação na API,
`SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT=1` como default em `auto_execute_paper.py`, aprovação paper em
memória sem persistência, mistura de escalas 0-100/0-1 no ensemble de crise (`crisis.py`), MACD/RSI sem
teste de série, HRP sem bissecção hierárquica real, look-ahead bias no backtest de penny stock, contrato
`Order`/adapter incompatível (`gate_metadata` ausente), idempotência não atômica, `SUPEREZIO_PRIMARY_API_KEY`
podendo ser reutilizada como chave DeepSeek (risco de vazamento cross-provider). **Esses NÃO foram
verificados por mim nesta sessão** — a auditoria externa parece rigorosa e vale investigar, mas não vou
afirmar concordância sem checar cada um pessoalmente, seguindo o mesmo padrão desta fase (ler antes de
concordar ou refutar).

## Resumo executivo

| Item | Severidade | Status |
|---|---|---|
| spider_sense hardcoded / critic fail-open | ALTA | CORRIGIDO (`4bda75c`) |
| DataHub aceita `{}` | MÉDIA-ALTA | CORRIGIDO (`ea63541`) |
| `exec()` em custom_tools | ALTA (avaliado) | MANTIDO com reforço de teste (`ea63541`) |
| Apprenticeship expirado no prompt do Bob | BAIXA (qualidade de conversa) | CORRIGIDO (`10490cf`) |
| `KeyError('provider')` no red team | ALTA | CORRIGIDO (`d8ca01b`) |
| SDCA `_truthy_high` invertido | MÉDIA | CORRIGIDO (`d8ca01b`) |
| Token Hugging Face exposto (6 arquivos) | **CRÍTICA** | **PENDENTE — ação do operador** |
| RAG `allow_pickle=True` | **CRÍTICA** | **PENDENTE — aguardando instrução** |
| Achados ALTO/MÉDIO da auditoria externa (auth, gates duplicados, crisis.py escala, etc.) | diversos | **NÃO VERIFICADO — requer investigação própria antes de agir** |

## Próximo passo

1. Operador: revogar o token Hugging Face na conta real.
2. Decidir se/quando corrigir `allow_pickle=True` e os 6 arquivos com token exposto.
3. Verificar individualmente (não apenas confiar) os achados ALTO/MÉDIO da auditoria externa antes de
   agir sobre eles, seguindo o mesmo padrão rigoroso desta sessão.
