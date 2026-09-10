# SUPEREZIO — Delivery Checklist v3 (Cloud Models)

**Atualizado:** 2026-09-10 · **Substitui:** `docs/DELIVERY_CHECKLIST_v2.md` (mundo 8082 e roteamento antigo)
**Runtime alvo:** 100% nuvem — `deepseek-v4-flash` na API oficial `https://api.deepseek.com` atende TODOS os papeis (Bob/CEO, orquestrador, experts financeiros, judge e auditor) e a API/UI fica em `:8002`. O caminho Z.ai/GLM (`glm-5.3`) e opcional e so existe com `SUPEREZIO_GLM_CODING_PLAN_API_KEY`. **Nao existe modelo local no caminho de resposta nem fallback cruzado entre providers.**

---

## ⬜ PRÉ-VOO

- [ ] `.env.local`: `SUPEREZIO_DEEPSEEK_API_KEY` preenchida sem ser impressa/commitada — e a UNICA chave exigida para o boot. `SUPEREZIO_GLM_CODING_PLAN_API_KEY` e opcional (so habilita o caminho Z.ai/GLM)
- [ ] Rede liberada para `https://api.deepseek.com` em HTTPS/443. Nenhuma GPU e nenhum servidor de modelo local sao necessarios
- [ ] TWS Paper (opcional nesta fase; obrigatório para loops de ordem): porta 7497, TIF DAY default desmarcado (M1)

## ⬜ BOOT (ordem documentada)

- [ ] **Terminal — API + frontend:**
  ```powershell
  $env:PYTHONPATH = "src;$env:PYTHONPATH"
  python -m agent_server.main
  ```
  Aguardar `Uvicorn running on http://127.0.0.1:8002`. Nao existe mais servidor de modelo local para subir antes.
- [ ] Health:
  ```powershell
  curl.exe -fsS http://127.0.0.1:8002/health
  curl.exe -fsS http://127.0.0.1:8002/health/details
  ```
  Esperado: API online, provider DeepSeek `configured` em `checks.providers_summary` e nenhum fallback cruzado
- [ ] **Confirmar model id** (fecha a pendencia do INV-R15/manifesto):
  ```powershell
  curl.exe -fsS http://127.0.0.1:8002/cockpit/summary
  ```
  Esperado: `"primary_model": "deepseek-v4-flash"`. Se divergir do `config/model_manifest.json`, interromper o gate e corrigir o contrato antes de prosseguir.

## ⬜ VERIFICAÇÃO PRÉ-TRADE

- [ ] Gates estáticos:
  ```powershell
  python -m ruff check src tests
  python scripts/check_agents.py
  ```
- [ ] Suíte completa:
  ```powershell
  python -m pytest tests/ -q
  ```
  Registrar o número real de collected/passed/failed/skipped — sem green-wash. Como referência datada, em 2026-08-21 foram 1.975 collected, 1.965 passed e 10 skipped; a contagem atual deve vir do comando, não deste documento.
- [ ] Smoke do browser **com resposta real do Bob**:
  ```powershell
  $env:SUPEREZIO_SMOKE_CHAT = "1"
  python scripts/browser_smoke.py --headed
  ```
- [ ] Cockpit em http://127.0.0.1:8002: Bob responde pelo tier DeepSeek em nuvem (`deepseek-v4-flash`); o Deep Panel identifica o provider externo e registra experts reais
- [ ] MAN_AT_WORK: com o provider DeepSeek configurado, alerta deve limpar; se não limpar sozinho, investigar `data/man_at_work/latest_alert.txt` antes de qualquer ordem

## ⬜ TESTES DE FAIL-CLOSED

- [ ] Com sistema operacional, remover/invalidar temporariamente `SUPEREZIO_DEEPSEEK_API_KEY` em `.env.local` e reiniciar a API
- [ ] `curl.exe http://127.0.0.1:8002/health/details` → tier de modelos indisponível (503), sistema em MAN_AT_WORK
- [ ] Confirmar que nenhum papel cai para outro provider: chave DeepSeek ausente/inválida → MAN_AT_WORK
- [ ] Restaurar a chave válida e reiniciar a API → recuperação para online
- [ ] Com a chave Z.ai ausente, pedir um modelo `glm-*` deve falhar fechado (o caminho GLM é opcional e não atende nenhum papel por padrão)

## ⬌ LOOPS DE TRADING (fase seguinte, com TWS paper)

- Mantém-se o bloco TRADING LOOPS do v2 (`test_trading_loop1/3/4/5.py`, 25 ordens paper via envelope canônico `PreparedOrderEnvelope`) — a topologia de modelos nao altera os money gates.

## ⬜ SIGN-OFF

```
SUPEREZIO DELIVERY v3 CLOUD — 2026-09-10
===========================================
Model tier:    deepseek-v4-flash (api.deepseek.com)   [ ]
Local model server: nao existe no caminho de resposta [ ]
Experts/judge/auditor: deepseek-v4-flash              [ ]
API:           :8002 online                           [ ]
Bob chat real: smoke chat respondendo                 [ ]
Fail-closed:   chave DeepSeek ausente/invalida → MAN_AT_WORK [ ]
Ruff:          0 erros                                [ ]
Check agents:  0 issues                               [ ]
Pytest:        ___ collected ___ passed ___ failed ___ skipped
TWS/loops:     [ ] fase seguinte
```
