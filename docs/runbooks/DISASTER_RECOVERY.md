# SuperEzio — Disaster Recovery & Continuidade

## O que está em risco

| Ativo | Localização | Perda se sumir |
|---|---|---|
| Código fonte | `C:\Users\marco\Desktop\SuperEzio Financeiro\` + Git | Catastrófico |
| Banco de dados | `data/investor.db` | Decisões, perfil, trades |
| Conversas | `data/conversation_memory.jsonl` | Memória do Bob |
| Traces | `runtime/traces/` | Auditoria |
| Learning Log | `data/learning_log.jsonl` | Lições aprendidas |
| Modelo GGUF | `models/Huihui-Qwen3-Next-80B-*.gguf` | CEO offline |

## Solução: backup local + externo

### 1. Backup local automático (a cada 6 horas)

```powershell
# scripts/backup.ps1
$backupDir = "D:\backups\superezio"  # segundo disco
$date = Get-Date -Format "yyyyMMdd-HHmm"
$src = "C:\Users\marco\Desktop\SuperEzio Financeiro"

# Só faz backup dos dados, não do .venv nem models/
robocopy "$src\data" "$backupDir\$date\data" /MIR /NP /NFL /NDL
robocopy "$src\.f51" "$backupDir\$date\.f51" /MIR /NP /NFL /NDL
robocopy "$src\config" "$backupDir\$date\config" /MIR /NP /NFL /NDL
robocopy "$src\runtime" "$backupDir\$date\runtime" /MIR /NP /NFL /NDL
robocopy "$src\docs" "$backupDir\$date\docs" /MIR /NP /NFL /NDL

# Rotação: mantém últimos 7 dias
Get-ChildItem $backupDir | Sort-Object Name -Desc | Select -Skip 168 | Remove-Item -Recurse -Force
```

### 2. Backup externo (GitHub privado ou pendrive)

```
Opção A: GitHub repo privado → git push semanal
Opção B: Pendrive criptografado → copiar backup mais recente 1x/dia
Opção C: Pasta sincronizada no OneDrive/Dropbox → backup automático em cloud
```

**Recomendação**: Pendrive de 64GB dedicado. Sem rede = sem ataque. Troca uma vez por dia.

### 3. Verificação de integridade

```powershell
# scripts/verify_backup.ps1
# Roda depois do backup. Verifica:
# - investor.db abre sem erro
# - conversation_memory.jsonl tem > 0 linhas
# - learning_log.jsonl parseia sem erro
# - .f51/checkpoints/latest.json é JSON válido
```

---

## Continuidade: Bob não pode morrer

### Problema: GPU cai, Bob morre

**Solução: Fallback automático pro Code Plan**

```python
# No gateway.py: se llama-server :8082 não responde em 2s,
# redireciona pro GLM Code Plan como CEO fallback
```

O Code Plan (`glm-5.2` via `api.z.ai/api/anthropic`) já funciona como Bob implementador. O mesmo endpoint pode servir como CEO fallback se o Qwen local cair.

### Problema: DeepSeek cai, experts morrem

**Solução: Gemini cobre os 4 experts do DeepSeek**

```python
# No experts.py: se DeepSeek falhar, Gemini assume
FALLBACK_PROVIDERS = {
    "deepseek": "gemini",  # Gemini cobre fundamental, macro, momentum, contrarian
}
```

Gemini 3.5 Flash é grátis (1500 req/dia). Já é provider de sentiment e social_forensics. Pode cobrir os outros 4 em emergência.

### Problema: Internet cai, tudo morre

**Solução: Modo offline**

```python
# Se sem internet:
# - Bob local responde sozinho (sem experts cloud)
# - Dados são do último cache
# - Paper trading pausa (sem IBKR)
# - Mensagem clara: "MODO OFFLINE. Análise limitada ao meu conhecimento local."
```
