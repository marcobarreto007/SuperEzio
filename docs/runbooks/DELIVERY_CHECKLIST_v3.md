# SUPEREZIO — Delivery Checklist v3 (Zero-Cloud)

**Data:** 2026-08-20 · **Substitui:** `docs/DELIVERY_CHECKLIST_v2.md` (mundo 8082 + providers de nuvem — obsoleto desde a diretiva zero-cloud de 2026-08-17)
**Runtime alvo:** Qwen3.8-27B-Q4_K_M local no servidor compartilhado do perfil cc (`:8080`), API em `:8002`. **Se :8080 cair, o sistema para em MAN_AT_WORK — não existe fallback em nuvem, por design.**

---

## ⬜ PRÉ-VOO

- [ ] GPUs livres: `nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader`
      (perfil canônico: RTX 3060 12 GB + RTX 2070 8 GB, tensor split `12,8`; investigar consumo concorrente antes do boot)
- [ ] `.env` zero-cloud: `SUPEREZIO_AGENT_BASE_URL=http://127.0.0.1:8080/v1`, model `Qwen3.8-27B-Q4_K_M`, **nenhuma** chave de LLM em nuvem (Questrade pode existir — feature não-LLM)
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
  Esperado: `Qwen3.8-27B-Q4_K_M`. Se divergir do `config/model_manifest.json`, interromper o gate e corrigir o contrato antes de prosseguir.
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
  Esperado: CEO/agente online, `cloud_fallback_present: false`

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
  Registrar o número real de collected/passed/failed/skipped — sem green-wash. Como referência datada, a coleta de 2026-08-20 encontrou 1.885 testes; a contagem atual deve vir do comando, não deste documento.
- [ ] Smoke do browser **com resposta real do Bob**:
  ```powershell
  $env:SUPEREZIO_SMOKE_CHAT = "1"
  python scripts/browser_smoke.py --headed
  ```
- [ ] Cockpit em http://127.0.0.1:8002: Genie + Deep Panel + Bob respondendo com modelo LOCAL (sem menção a provider de nuvem)
- [ ] MAN_AT_WORK: com CEO online, alerta deve limpar; se não limpar sozinho, investigar `data/man_at_work/latest_alert.txt` antes de qualquer ordem

## ⬜ TESTE DE FAIL-CLOSED (substitui o "Fallback Test" do v2)

- [ ] Com sistema operacional, derrubar :8080 (Ctrl+C no Terminal 1)
- [ ] `curl.exe http://127.0.0.1:8002/health/details` → CEO offline, sistema em MAN_AT_WORK
- [ ] **Nenhuma chamada para fora** (zero-cloud é o contrato): se qualquer provider de nuvem aparecer no log = BUG crítico
- [ ] Religar :8080 → recuperação para online

## ⬌ LOOPS DE TRADING (fase seguinte, com TWS paper)

- Mantém-se o bloco TRADING LOOPS do v2 (`test_trading_loop1/3/4/5.py`, 25 ordens paper via envelope canônico `PreparedOrderEnvelope`) — inalterado pelo zero-cloud.

## ⬜ SIGN-OFF

```
SUPEREZIO DELIVERY v3 ZERO-CLOUD — 2026-08-20
==============================================
Model server:  :8080 Qwen3.8-27B local    [ ]
Model id:      confirmado via /v1/models  [ ]
API:           :8002 online               [ ]
Bob chat real: smoke chat respondendo     [ ]
Fail-closed:   MAN_AT_WORK sem nuvem      [ ]
Ruff:          0 erros                    [ ]
Check agents:  0 issues                   [ ]
Pytest:        ___ collected ___ passed ___ failed ___ skipped
TWS/loops:     [ ] fase seguinte
```
