# AGENT_OPERATING_SYSTEM.md — Agent OS Runtime

Status: **active**
Version: 1.0

## O que é o Agent OS

O Agent Operating System é a camada de runtime que permite ao exército de agentes
operar com:
- memória compartilhada (`.agent_bus/runtime/`)
- checkpoints obrigatórios (`.f51/checkpoints/latest.json`)
- comunicação padronizada (formato de ticket e relatório)
- gates determinísticos

## Estrutura de Runtime

```
.agent_bus/
  runtime/           # Memória temporária (git-ignored)
    agent_*.txt      # Relatórios de agentes em execução
    swarm_*.json     # Estado de execuções de swarm
    tickets/         # Tickets disparados

.f51/
  checkpoints/
    latest.json      # Checkpoint mais recente (obrigatório)
    SESSION_*.md     # Checkpoints de sessões específicas
  TASK_BOARD.md      # Quadro de tarefas atual
  RISK_REGISTER.md   # Registro de riscos
```

## Formato de Ticket

Todo agente recebe um ticket com:

```text
Goal: [objetivo claro]
Context files: [arquivos de contexto]
Allowed files: [arquivos que pode ler]
Forbidden files: [arquivos que NÃO pode tocar]
Expected output: [formato de relatório esperado]
Verification gate: [como validar a saída]
Stop condition: [quando parar]
```

## Formato de Relatório

Todo agente devolve:

```text
role: [nome do agente]
scope: [o que foi analisado]
files_read: [lista de arquivos lidos]
actions: [ações executadas]
claims: [afirmações]
evidence: [arquivo:linha ou output de comando]
risks: [riscos com severity]
next_gate: [próximo passo verificável]
```

## Gates Determinísticos

Antes de aceitar qualquer mudança:
```powershell
git status --short
git diff --check
python -m ruff check src tests
python -m pytest tests/ -q
python scripts\browser_smoke.py
```

Quando há runtime/modelo:
```powershell
Get-NetTCPConnection -LocalPort 8000,8020 -ErrorAction SilentlyContinue
nvidia-smi --query-gpu=index,name,memory.used,memory.free --format=csv,noheader,nounits
```

## Comunicação Entre Agentes

Agentes NÃO conversam diretamente.
Agentes enviam relatórios ao orquestrador.
O orquestrador integra e decide.

Se um agente precisar de output de outro:
1. Agente A escreve relatório em `.agent_bus/runtime/`
2. Orquestrador lê e passa contexto relevante para Agente B
3. Agente B nunca lê relatório bruto de A (evita viés)

## Regras de Ouro do Agent OS

1. Um agente, uma missão.
2. Builder escreve pouco, verifier não é o mesmo que escreveu.
3. Savekeeper não salva segredo.
4. Explorer mata agente ruim com evidência.
5. Orquestrador integra tudo.
6. Git limpo no final.
7. Checkpoint obrigatório — sem exceção.
