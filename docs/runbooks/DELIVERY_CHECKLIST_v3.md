# SUPEREZIO — Delivery Checklist v3 (Hybrid Models)

**Atualizado:** 2026-08-21 · **Substitui:** `docs/DELIVERY_CHECKLIST_v2.md` (mundo 8082 e roteamento antigo)
**Runtime alvo:** Qwen3.8-27B-UD-IQ2_XXS local para CEO/orquestrador (`:8080`), DeepSeek V4 Pro externo para experts/judge/auditor e API em `:8002`. **Nao existe fallback cruzado entre os tiers.**

---

## ⬜ PRÉ-VOO

- [ ] GPUs livres: `nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader`
      (perfil canônico: RTX 3060 12 GB + RTX 2070 8 GB, tensor split `12,8`; investigar consumo concorrente antes do boot)
- [ ] `.env.local` hibrido: agent em `http://127.0.0.1:8080/v1`, model `Qwen3.8-27B-UD-IQ2_XXS`, DeepSeek em `https://api.deepseek.com`, model `deepseek-v4-pro` e `SUPEREZIO_DEEPSEEK_API_KEY` preenchida sem ser impressa/commitada
- [ ] TWS Paper (opcional nesta fase; obrigatório para loops de ordem): porta 7497, TIF DAY default desmarcado (M1)

## ⬜ BOOT (ordem documentada — cc primeiro)

- [ ] **Terminal 1 — servidor de modelo (perfil cc):**
  ```powershell
  C:\Users\marco\models\qwen3.8-27b\run-cc.ps1   # ou botão direito → Run with PowerShell
  ```
  Aguardar health: `curl.exe -fsS http://127.0.0.1:8080/health` → 200. Carga do modelo ~30-90 s.
  **Nota:** primeira inferência fria pode levar minutos (prompt grande); depois entra em cache.
- [ ] **Confirmar model id** (fecha a pendência do INV-R15/manifesto):
  ```powershell
  curl.exe -fsS http://127.0.0.1:8080/v1/models
  ```
  Esperado: `Qwen3.8-27B-UD-IQ2_XXS`. Se divergir do `config/model_manifest.json`, interromper o gate e corrigir o contrato antes de prosseguir.
- [ ] **Terminal 2 — API + frontend:**
  ```powershell
  python -m agent_server.main
  ```
  Aguardar `Uvicorn running on http://127.0.0.1:8002`
- [ ] Health:
  ```powershell
  curl.exe -fsS http://127.0.0.1:8002/health
  curl.exe -fsS http://127.0.0.1:8002/health/details
  ```
  Esperado: CEO local online e `provider_deepseek` externo/configurado; nenhum fallback cruzado

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
- [ ] Cockpit em http://127.0.0.1:8002: Bob responde via Qwen local; Deep Panel identifica DeepSeek externo e registra experts reais
- [ ] MAN_AT_WORK: com CEO online, alerta deve limpar; se não limpar sozinho, investigar `data/man_at_work/latest_alert.txt` antes de qualquer ordem

## ⬜ TESTES DE FAIL-CLOSED

- [ ] Com sistema operacional, derrubar :8080 (Ctrl+C no Terminal 1)
- [ ] `curl.exe http://127.0.0.1:8002/health/details` → CEO offline, sistema em MAN_AT_WORK
- [ ] Confirmar que o CEO nao cai para DeepSeek e entra em MAN_AT_WORK
- [ ] Religar :8080 → recuperação para online
- [ ] Invalidar temporariamente a chave DeepSeek → `/health/details` 503 e expert explicitamente indisponivel, sem chamada a Qwen
- [ ] Restaurar a chave local e confirmar `provider_deepseek.status=configured`

## ⬌ LOOPS DE TRADING (fase seguinte, com TWS paper)

- Mantém-se o bloco TRADING LOOPS do v2 (`test_trading_loop1/3/4/5.py`, 25 ordens paper via envelope canônico `PreparedOrderEnvelope`) — a topologia de modelos nao altera os money gates.

## ⬜ SIGN-OFF

```
SUPEREZIO DELIVERY v3 HYBRID — 2026-08-21
===========================================
Model server:  :8080 Qwen3.8-27B local    [ ]
Model id:      confirmado via /v1/models  [ ]
Experts:       DeepSeek V4 Pro externo     [ ]
API:           :8002 online               [ ]
Bob chat real: smoke chat respondendo     [ ]
Fail-closed:   tiers isolados              [ ]
Ruff:          0 erros                    [ ]
Check agents:  0 issues                   [ ]
Pytest:        ___ collected ___ passed ___ failed ___ skipped
TWS/loops:     [ ] fase seguinte
```
