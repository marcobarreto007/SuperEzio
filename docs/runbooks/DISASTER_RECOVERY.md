# SuperEzio â€” Disaster Recovery & Continuidade

> **HISTORICO / SUPERSEDED.** Este runbook contem caminhos, modelos e fallbacks antigos e nao deve ser executado. Para recuperacao atual use `docs/runbooks/RUNBOOK.md` e `docs/runbooks/OPERATIONAL_RUNBOOK.md`: CEO/orquestrador Qwen local em `:8080`, experts DeepSeek externos, API/UI em `:8002` e isolamento fail-closed.

## O que estÃ¡ em risco

| Ativo | LocalizaÃ§Ã£o | Perda se sumir |
|---|---|---|
| CÃ³digo fonte | `C:\Users\marco\Desktop\SuperEzio Financeiro\` + Git | CatastrÃ³fico |
| Banco de dados | `data/investor.db` | DecisÃµes, perfil, trades |
| Conversas | `data/conversation_memory.jsonl` | MemÃ³ria do Bob |
| Traces | `runtime/traces/` | Auditoria |
| Learning Log | `data/learning_log.jsonl` | LiÃ§Ãµes aprendidas |
| Modelo GGUF | `models/Huihui-Bob Core-*.gguf` | CEO offline |

## SoluÃ§Ã£o: backup local + externo

### 1. Backup local automÃ¡tico (a cada 6 horas)

```powershell
# scripts/backup.ps1
$backupDir = "D:\backups\superezio"  # segundo disco
$date = Get-Date -Format "yyyyMMdd-HHmm"
$src = "C:\Users\marco\Desktop\SuperEzio Financeiro"

# SÃ³ faz backup dos dados, nÃ£o do .venv nem models/
robocopy "$src\data" "$backupDir\$date\data" /MIR /NP /NFL /NDL
robocopy "$src\.f51" "$backupDir\$date\.f51" /MIR /NP /NFL /NDL
robocopy "$src\config" "$backupDir\$date\config" /MIR /NP /NFL /NDL
robocopy "$src\runtime" "$backupDir\$date\runtime" /MIR /NP /NFL /NDL
robocopy "$src\docs" "$backupDir\$date\docs" /MIR /NP /NFL /NDL

# RotaÃ§Ã£o: mantÃ©m Ãºltimos 7 dias
Get-ChildItem $backupDir | Sort-Object Name -Desc | Select -Skip 168 | Remove-Item -Recurse -Force
```

### 2. Backup externo (GitHub privado ou pendrive)

```
OpÃ§Ã£o A: GitHub repo privado â†’ git push semanal
OpÃ§Ã£o B: Pendrive criptografado â†’ copiar backup mais recente 1x/dia
OpÃ§Ã£o C: Pasta sincronizada no OneDrive/Dropbox â†’ backup automÃ¡tico em cloud
```

**RecomendaÃ§Ã£o**: Pendrive de 64GB dedicado. Sem rede = sem ataque. Troca uma vez por dia.

### 3. VerificaÃ§Ã£o de integridade

```powershell
# scripts/verify_backup.ps1
# Roda depois do backup. Verifica:
# - investor.db abre sem erro
# - conversation_memory.jsonl tem > 0 linhas
# - learning_log.jsonl parseia sem erro
# - .f51/checkpoints/latest.json Ã© JSON vÃ¡lido
```

---

## Continuidade: Bob nÃ£o pode morrer

### Problema: GPU cai, Bob morre

**SoluÃ§Ã£o: Fallback automÃ¡tico pro Code Plan**

```python
# No gateway.py: se llama-server :8082 nÃ£o responde em 2s,
# redireciona pro GLM Code Plan como CEO fallback
```

O Code Plan (`glm-5.2` via `api.z.ai/api/anthropic`) jÃ¡ funciona como Bob implementador. O mesmo endpoint pode servir como CEO fallback se o Qwen local cair.

### Problema: DeepSeek cai, experts morrem

**SoluÃ§Ã£o: Gemini cobre os 4 experts do DeepSeek**

```python
# No experts.py: se DeepSeek falhar, Gemini assume
FALLBACK_PROVIDERS = {
    "deepseek": "gemini",  # Gemini cobre fundamental, macro, momentum, contrarian
}
```

Gemini 3.5 Flash Ã© grÃ¡tis (1500 req/dia). JÃ¡ Ã© provider de sentiment e social_forensics. Pode cobrir os outros 4 em emergÃªncia.

### Problema: Internet cai, tudo morre

**SoluÃ§Ã£o: Modo offline**

```python
# Se sem internet:
# - Bob local responde sozinho (sem experts cloud)
# - Dados sÃ£o do Ãºltimo cache
# - Paper trading pausa (sem IBKR)
# - Mensagem clara: "MODO OFFLINE. AnÃ¡lise limitada ao meu conhecimento local."
```
