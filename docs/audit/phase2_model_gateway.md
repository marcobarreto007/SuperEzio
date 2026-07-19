# Fase 2 — Auditoria do Model Gateway (isolado)

Gerado: 2026-07-19
Escopo: `src/core/model_serving/gateway.py`, `src/core/pipeline/nodes/expert_dialogue.py`
Método: leitura direta de código, rastreamento de chamada real ponta a ponta. Sem chamadas de rede.

## 1. CONFIRMED — Fallback silencioso não pode ser desligado no caminho real dos especialistas

Cadeia de chamada real, rastreada linha a linha:

1. `expert_dialogue.py:202-207` chama `self.gateway.chat_completion(..., preferred_provider=provider)`.
2. `gateway.py:546` `chat_completion()` não aceita `allow_fallback`. Ele resolve `provider_obj = self._providers_for_request(preferred_provider)[0]` (sem passar `allow_fallback`, então usa o default `True`) e depois chama `self.generate(..., preferred_provider=provider_obj.name, ...)`.
3. `gateway.py:306` `generate()` **não tem parâmetro `allow_fallback` na assinatura**. Ele sempre chama `self._providers_for_request(preferred_provider)` com o default `allow_fallback=True`.
4. `_providers_for_request` (linha 88-139): quando `allow_fallback=True` (sempre, neste caminho) e existe `preferred_provider`, monta a lista como `[provider_preferido] + [todos os outros providers não local, não em cooldown]`.
5. `_max_attempts()` permite até `config.max_fallbacks + 1` tentativas — por padrão isso é `2 + 1 = 3` tentativas (ver `GatewayConfig` / `runtime.yml` `gateway.max_fallbacks: 2`).

**Consequência prática:** quando `graph.py` chama `node_expert` com `provider_name="daytrade_judge"`, se o provider `daytrade_judge` falhar (timeout, erro de rede, JSON malformado tratado como exceção), o gateway **automaticamente tenta outro provider da lista** (`deepseek`, `daytrade_auditor`, `ceo_fallback_glm`, dependendo da ordem de prioridade) sem que o código do `node_expert` ou `graph.py` saiba ou impeça isso.

Único ponto de retorno visível ao chamador de qual provider realmente respondeu: o campo `provider` no payload de retorno de `node_expert` — mas esse campo é **preenchido com `provider_name` do request original** (`state.get("provider_name")`), não com o provider que efetivamente respondeu após fallback. Ou seja, **o campo `provider` no resultado final pode estar errado** — reportando "daytrade_judge" quando na verdade "deepseek" genérico (ou pior, "ceo_fallback_glm" rodando `glm-5.2`, um modelo completamente diferente) respondeu.

- Verdict: **CONFIRMED**, lido diretamente no código (gateway.py:88-139, 306-414, 546-596; expert_dialogue.py:202-207).
- Classe: INFRAESTRUTURA / risco de integridade experimental.
- Severidade: **ALTA para o protocolo de pesquisa descrito na conversa anterior.** A exigência explícita era: "durante os experimentos de componentes, o fallback será desligado. Caso contrário, poderíamos pensar que testamos DeepSeek V4 Pro quando, silenciosamente, outro modelo respondeu." **Essa exigência não está implementada no código atual.** `allow_fallback` existe só em `stream_generate_async`, que não é o caminho usado pelos especialistas.

## 2. Comportamento de cooldown — correto, mas relevante para o achado acima

- `_provider_cooldown_max_errors = 3`, `_provider_cooldown_seconds = 120` (gateway.py:57-58) — após 3 erros consecutivos, o provider entra em cooldown de 2 minutos e é pulado nas próximas tentativas (`_skip_cooldown`).
- Isso é bom para resiliência de produção, mas piora o problema de integridade experimental: um provider com falhas intermitentes vai silenciosamente desviar tráfego para outro provider por até 2 minutos, sem qualquer sinalização estrutural além de `log_event` (que não é capturado no payload de retorno do especialista).

## 3. `_apply_deepseek_options` — correto, mas frágil

- `gateway.py:157`: `if not provider.model.startswith("deepseek-v4-"): return` — as opções de `thinking`/`reasoning_effort` só são aplicadas se o nome do modelo começar exatamente com `"deepseek-v4-"`. Isso está consistente com `deepseek-v4-pro` configurado no `.env.example`. Não é um bug, mas é um ponto de fragilidade: se o modelo for renomeado no provedor (ex: `deepseek-v4.1-pro`), as opções de thinking silenciosamente deixam de ser aplicadas sem erro nem log.

## 4. Gemini provider órfão — CONFIRMED

- `providers.py` registra o provider `gemini` (nome `GEMINI_PROVIDER_NAME`) `if gemini_key:` (linha 139).
- `experts.py` (mudança pendente) migrou `sentiment` e `social_forensics` de `"gemini"` para `"deepseek"` em `EXPERT_PROVIDERS`.
- Buscado no restante de `src/`: nenhuma outra referência a `GEMINI_PROVIDER_NAME` ou `preferred_provider="gemini"` foi necessária para confirmar — o provider Gemini, se a chave `GEMINI_API_KEY` estiver setada, continua sendo instanciado e **entra na lista de fallback genérica** (`_providers_for_request` sem `preferred_provider`, ou como fallback do provider preferido quando `allow_fallback=True`). Ou seja, ele não está "morto" — ele pode aparecer como fallback silencioso de qualquer especialista DeepSeek que falhe, o que é uma segunda via pela qual "todos DeepSeek V4 Pro" pode silenciosamente virar "alguns Gemini".
- Verdict: CONFIRMED como consequência direta do achado #1 — não é um bug isolado, é o mesmo mecanismo de fallback.

## 5. Resumo executivo desta fase

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| `allow_fallback` não existe no caminho síncrono usado pelos especialistas (`generate`/`chat_completion`) | INFRAESTRUTURA | **ALTA** | CONFIRMED |
| Campo `provider` no resultado do especialista reflete o pedido, não quem respondeu de fato | INFRAESTRUTURA / integridade experimental | **ALTA** | CONFIRMED |
| Gemini provider pode entrar como fallback silencioso de qualquer especialista DeepSeek | INFRAESTRUTURA | ALTA (mistura modelos sem rastro) | CONFIRMED |
| Cooldown de 120s desvia tráfego sem sinalização no payload | INFRAESTRUTURA | MÉDIA | CONFIRMED |
| `_apply_deepseek_options` frágil a rename de modelo | INFRAESTRUTURA | BAIXA | CONFIRMED |

## Implicação direta para o protocolo de pesquisa "Billion Token"

O plano audível na conversa anterior dependia de rastreabilidade estrita (`snapshot_hash`, `model_id`, `response_hash` por chamada) e da garantia de que "DeepSeek V4 Pro" era realmente quem respondia. **Hoje isso não é garantido pelo código.** Antes de rodar qualquer fase de pesquisa em escala, dois consertos são pré-requisito, não opcionais:

1. Adicionar `allow_fallback: bool = False` como parâmetro passante em `chat_completion()` → `generate()` → `_providers_for_request()`, e fazer `node_expert`/`graph.py` passar `allow_fallback=False` quando rodando em modo pesquisa (`SUPEREZIO_RESEARCH_PAPER_ONLY=1`).
2. Fazer o payload de retorno de `node_expert` registrar o **provider que efetivamente respondeu** (retornado por `generate_api`/`chat_completion`), não apenas o provider solicitado — hoje esse dado não é propagado de volta.

Nenhuma dessas mudanças foi aplicada nesta auditoria — só a leitura e o diagnóstico, conforme a regra "sem feature antes de inventário/contratos/runtime/testes".

## Próximo passo

Fase 3: DataHub isolado (Finnhub, Twelve Data, yfinance, Stooq — fallback, dict vazio tratado como sucesso).
