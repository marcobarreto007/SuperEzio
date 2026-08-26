---
name: f51-secure-scan
description: "Scanner de segurança SAST com Bandit + validação de secrets e vulnerabilidades. Detecta injeção, secrets expostos, e más práticas de segurança. Triggers: security, bandit, SAST, vulnerability, secret, scan, segurança, vulnerabilidade."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts]
related-skills: [f51-quality-gate, f51-dead-code, f51-env-guard]
---

# f51-secure-scan

## Quando usar

- Nunca rodou SAST no código
- Secrets podem estar hardcodados (API keys, tokens)
- Código usa `subprocess` com input de usuário
- Antes de qualquer release ou deploy público
- Depois de adicionar nova dependência

## Nunca fazer

- Ignorar finding de severity HIGH sem justificativa documentada
- Commitar `# nosec` sem explicar por que o risco é aceito
- Rodar scan e não corrigir nada — scan sem remediação é teatro
- Expor resultado de scan publicamente (revela vulnerabilidades)

## Workflow

1. **Rodar Bandit**: `bandit -r src/ -f json -o bandit_report.json` — scan completo.
2. **Rodar verificação de secrets**: `grep -rn "api_key\|API_KEY\|secret\|SECRET\|token\|TOKEN\|password\|PASSWORD" src/ --include="*.py"`.
3. **Classificar findings por severity**: HIGH (bloqueante), MEDIUM (requer justificativa), LOW (documentar).
4. **Corrigir HIGH**: remover secrets hardcodados, validar input, escapar output.
5. **Documentar MEDIUM**: `# nosec: justificativa` para cada falso positivo ou risco aceito.
6. **Adicionar ao CI/pre-commit**: bandit scan antes de commit.
7. **Atualizar `.pre-commit-config.yaml`** com hook do bandit.

## Bandit baseline para este projeto

```bash
# Scan completo com perfil agressivo
bandit -r src/ -ll -ii -f json -o security/bandit_report.json

# Verificar apenas HIGH severity
bandit -r src/ -ll -ii --severity-level high

# Plugins específicos para trading/finance
bandit -r src/ -s B101,B102,B103,B104,B105  # assert, exec, eval, etc.
```

## Secrets check

```bash
# Procurar secrets hardcodados
grep -rnE "(api_key|secret|token|password|passwd)\s*=\s*['\"]" src/ --include="*.py"

# Procurar .env committed
git ls-files | grep -E "\.env$|\.env\."

# Procurar private keys
grep -rn "-----BEGIN.*PRIVATE KEY-----" src/ --include="*.py"
```

## Entregáveis mínimos

```
== F51 SECURE SCAN REPORT ==

## Bandit
- Total findings: N
- HIGH: N | MEDIUM: N | LOW: N
- HIGH corrigidos: N | HIGH pendentes: N

## Secrets
- Secrets encontrados: N
- Corrigidos: N
- Falsos positivos: N

## CI Integration
- pre-commit hook: [adicionado / pendente]
- CI pipeline: [configurado / pendente]

## Arquivos críticos revisados
- [arquivo]: [risco] [mitigação]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Finding HIGH não corrigido = release bloqueada.
- Secret em código = corrigir IMEDIATAMENTE (revogar, regenerar, usar env var).
- `# nosec` sem justificativa = tratado como vulnerabilidade.
- Scan de segurança roda em TODO commit (pre-commit) e TODO PR (CI).
