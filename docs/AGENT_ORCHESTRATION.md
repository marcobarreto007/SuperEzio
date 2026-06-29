# SuperEzio Agent Orchestration

## Arquitetura do Exército

```text
Usuario
  └─ Orquestrador (Claude Code)
       ├─ Wave 1: Recon + Audit
       │   ├─ recon-researcher
       │   ├─ security-reviewer
       │   └─ code-quality-reviewer
       ├─ Wave 2: Runtime + Contracts
       │   ├─ runtime-verifier
       │   ├─ api-contract-verifier
       │   └─ training-verifier
       ├─ Wave 3: Integration
       │   ├─ frontend-ux-reviewer
       │   └─ model-gateway-verifier
       └─ Wave 4: Meta + Save
           ├─ agent-explorer
           └─ savekeeper
```

## Como disparar

```text
/swarm Auditar o estado atual do SuperEzio antes do release
```

O comando `/swarm` está definido em `.claude/commands/swarm.md`.

## Fluxo de execução

1. **Orquestrador** recebe o objetivo do usuário
2. **Wave 1** (3 agentes em paralelo): mapeia arquitetura, segurança, qualidade
3. **Wave 2** (3 agentes em paralelo): verifica runtime, API, treinos
4. **Wave 3** (2 agentes em paralelo): testa frontend, model gateway
5. **Wave 4** (2 agentes): avalia agentes e salva estado

## Regras de ouro

- Um agente = uma missão
- Builder escreve pouco
- Verifier não é o mesmo que escreveu
- Savekeeper não salva segredo
- Explorer mata agente ruim
- Orquestrador integra tudo
- Git limpo no final

## Gates obrigatórios

```powershell
git status --short
git diff --check
python -m ruff check src/ tests/
python -m pytest tests/ -q
```

## Pontuação de agente

| Critério | Peso | Pergunta |
|----------|------|----------|
| Evidência | 0-5 | Citou arquivos/comandos/fontes? |
| Utilidade | 0-5 | Reduziu incerteza? |
| Precisão | 0-5 | Evitou chute? |
| Escopo | 0-5 | Respeitou limites? |
| Verificação | 0-5 | Rodou gate? |
| Concisão | 0-5 | Relatório usável? |

**Total: 30** | Elite: 26+ | Bom: 21-25 | Fraco: 10-15 | Substituir: <10
