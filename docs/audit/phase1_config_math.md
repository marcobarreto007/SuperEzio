# Fase 1 — Auditoria de Configuração e Matemática (sem LLM)

Gerado: 2026-07-19
Escopo: `config/runtime.yml`, `.env.example`, `src/core/model_serving/providers.py`, `src/core/math/math_hub.py`
Método: leitura direta de arquivos em disco, sem execução de rede, sem GitHub.

## 1. Configuração — divergências reais encontradas

### 1.1 Contexto do modelo local: 4096 vs 65536 tokens

- `config/runtime.yml:42` declara `context_length: 4096` e `gpu_layers: 35` para o modelo `agent` (`bob-core-local.gguf`, quantização `Q4_K_M`).
- `.f51/ENTRYPOINT_MAP.md:33` (atualizado 2026-06-28) declara `Context: 65536 tokens (64K)`, `GPU: 49/49 layers`, modelo `Bob Core-q4_k.gguf` (17.3 GB), arquitetura `qwen3moe (128 experts, 8 active, 48 layers)`.
- **Isso não é o mesmo deploy.** `runtime.yml` aponta para um artefato (`bob-core-local.gguf` + LoRA `bob-lora-best.gguf`) diferente do artefato citado no `ENTRYPOINT_MAP.md` (`Bob Core-q4_k.gguf` sem LoRA mencionado). Um dos dois documentos está desatualizado, ou existem dois perfis de deploy (local vs GPU alugada) sem marcação clara de qual é o ativo.
- **Verdict: CONFIRMED — divergência de contrato de runtime.** Precisa ser resolvido rodando `scripts/serve_agent_llamacpp.ps1` de verdade e capturando `/health/details` ou os logs de boot do llama-server, não inferido de documentação.
- Classe: INFRAESTRUTURA. Risco: qualquer prompt do CEO acima de ~4k tokens pode ser truncado silenciosamente se `runtime.yml` for o que está realmente ativo.

### 1.2 `.env.example` parcialmente fora de sync com o `runtime.yml`

- `.env.example` documenta `SUPEREZIO_DEEPSEEK_REASONING_EFFORT` e `SUPEREZIO_DEEPSEEK_THINKING` na seção "LOW — Behavior & Debug" (linhas 71-72, comentadas) **e também** na seção nova "DeepSeek Pro Research Profile" no fim do arquivo (linhas 96-118, ativas/não comentadas). Duplicação de documentação da mesma variável em duas seções com prioridades diferentes ("LOW" vs seção nova sem prioridade declarada).
- `SUPEREZIO_EXPERT_DIALOGUE_ROUNDS` aparece comentado na seção MEDIUM (linha 46, sem valor) e novamente ativo no bloco novo (linha 102, `=2`). O bloco novo vence porque está sem `#`, mas a duplicação indica que o arquivo não foi consolidado após a extensão.
- Classe: INFRAESTRUTURA / documentação de config. Risco baixo (não quebra runtime), mas confunde qualquer agente ou pessoa lendo o `.env.example` de cima para baixo.

### 1.3 `providers.py` — confirma a arquitetura da auditoria anterior

- `EXPERT_PROVIDERS` (em `experts.py`, já commitado como pendente) migrou sentiment/social_forensics de Gemini para DeepSeek — confirmado no diff, consistente com `providers.py`.
- `providers.py` cria providers **separados** para `daytrade_judge` (priority -305) e `daytrade_auditor` (priority -304), ambos com modelo default vindo de `SUPEREZIO_DAYTRADE_JUDGE_MODEL`/`SUPEREZIO_DAYTRADE_AUDITOR_MODEL`, caindo em `deepseek_model` se ausente. Isso está correto e implementado como a arquitetura descrita pedia.
- Fallback GLM (`ceo_fallback_glm`, priority -680) só é registrado `if glm_fallback_key` — sem a env var, o fallback simplesmente não existe na lista, não falha silenciosamente. Comportamento correto.
- Gemini provider (priority -290) só é registrado `if gemini_key`. Como `sentiment`/`social_forensics` agora apontam para `"deepseek"` em `EXPERT_PROVIDERS`, o provider Gemini fica órfão (registrado mas não referenciado por nenhum role) a menos que outro código ainda use `GEMINI_PROVIDER_NAME` diretamente. **Não verificado nesta fase** — candidato a checar na Fase 2 (Model Gateway).

## 2. Matemática — `src/core/math/math_hub.py`

`MathHub.calculate_all()` roda 14 módulos independentes, cada um com status `ok | insufficient_data | skipped | error`. Isso é uma boa prática — nenhum módulo mascara falta de dado como zero silencioso, exceto um caso:

### 2.1 CONFIRMED — `_quantum_module()` usa seed fixa (numpy `RandomState(42)`)

- Arquivo: `src/core/math/math_hub.py:431`
- `rng = np.random.RandomState(42)` — semente fixa hardcoded.
- Isso significa que o "Monte Carlo ponderado por caminhada quântica" (`quantum_weighted_monte_carlo`) produz **exatamente a mesma sequência de 100 cenários toda vez que roda**, para qualquer ticker, qualquer dado de mercado. Os únicos inputs que variam de fato são os `counts` vindos de `QuantumWalkBias.run_simulation()` (não auditado nesta fase — pode ou não ser determinístico também).
- **Classificação real do componente: não é ALPHA nem EVIDÊNCIA de mercado — é um gerador de cenário estático dressado de simulação probabilística.** Se `QuantumWalkBias` também for determinística (a checar), `quantum_bias` no relatório final é uma constante disfarçada de número dinâmico.
- **Falha concreta:** se `f51_confidence` ou qualquer decisão upstream usar `quantum_bias` como sinal, esse sinal não carrega informação nova sobre o ticker — é ruído fixo. Isso precisa ser corrigido (remover a seed, ou documentar explicitamente que é uma simulação de cenário fixo para fins de teste, não um insumo de decisão real) antes de qualquer especialista LLM tratar esse número como evidência.
- Verdict: CONFIRMED (lido diretamente no código, linha exata).

### 2.2 Módulos com fallback silencioso de dado ausente — a checar

- `_dcf_module`: retorna `status: skipped` se `fcf` ou `shares` ausentes — correto, não inventa valor.
- `_portfolio_module`: se a consulta SQLite falhar (`except Exception: pass`, linha ~501), cai silenciosamente para usar só o ticker atual sem alertar que os outros 19 tickers do HRP não foram carregados. Não é fabricação de dado, mas é uma degradação silenciosa de qualidade (HRP com 1 ativo não é HRP). Candidato a risco MÉDIO — registrar mas não bloqueia.
- `_f51_module`: usa heurísticas (`veracity=0.85 if data_quality in {...} else 0.55`, `consensus=0.65` fixo) — bate com o que a transcrição já suspeitava: parte do "F51 unified confidence" é heurística codificada, não puramente calculada dos dados. `consensus=0.65` é uma constante fixa em toda chamada — não é lido de lugar nenhum. Confirma o achado anterior sobre o F51 misturar heurística com dado real.

## 3. Resumo executivo desta fase

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| Context length 4096 vs 65536 (runtime.yml vs ENTRYPOINT_MAP.md) | INFRAESTRUTURA | ALTO | CONFIRMED — precisa teste no servidor real |
| `.env.example` com variáveis duplicadas em 2 seções | INFRAESTRUTURA | BAIXO | CONFIRMED |
| Gemini provider órfão após migração sentiment/social_forensics | INFRAESTRUTURA | A VERIFICAR | Pendente Fase 2 |
| `_quantum_module` com seed fixa (42) | MATEMÁTICA/EVIDÊNCIA | ALTO | CONFIRMED |
| `_portfolio_module` degrada silenciosamente para 1 ativo se SQLite falhar | MATEMÁTICA | MÉDIO | CONFIRMED |
| `_f51_module` usa `consensus=0.65` fixo, não calculado | MATEMÁTICA/EVIDÊNCIA | MÉDIO | CONFIRMED (consistente com achado anterior da transcrição) |

## Próximo passo

Fase 2: Model Gateway isolado (fallback, timeout, cooldown, JSON inválido) — testar com respostas artificiais dos provedores, sem chamar DeepSeek de verdade.
