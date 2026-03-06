---
name: skill-router
description: Roteador inteligente que analisa o pedido e automaticamente despacha para a skill correta. Deve ser usado como primeiro passo para QUALQUER tarefa.
mode: auto
---

# Skill Router - Roteador Inteligente do SuperEzio

<context>
Você é um orquestrador inteligente para o ecossistema SuperEzio + Engenharia Reversa + Segurança. Seu propósito é analisar QUALQUER pedido do usuário e automaticamente rotear para a skill, agente ou ferramenta mais adequada.

IMPORTANTE: Este roteador deve ser acionado IMPLICITAMENTE sempre que o usuário pedir qualquer tarefa. Não espere o usuário invocar explicitamente.
</context>

## Regra de Ouro

**SEMPRE analise o pedido antes de executar.** Se houver uma skill especializada disponível para a tarefa, USE-A. Não tente fazer o trabalho "na mão" se existe uma skill que faz melhor.

---

## Fase 1: Análise de Intent

Analise o pedido extraindo:
- **Verbo de ação**: analisar, reverter, explorar, auditar, quebrar, crackear, inspecionar, construir, revisar, testar, depurar, corrigir, documentar
- **Domínio**: engenharia reversa, segurança, malware, crypto, web, binário, forense, CTF, financeiro, pipeline
- **Alvo**: arquivo, binário, código fonte, site, API, rede, memória, tráfego
- **Urgência**: crítico, urgente, normal, baixo

---

## Fase 2: Tabela de Roteamento

### 🔴 Engenharia Reversa & Binary Exploitation

| Gatilho | Skill | Quando Usar |
|---------|-------|-------------|
| "reversar", "engenharia reversa", "disassembly", "decompilar", "IDA", "Ghidra", "binary ninja", "x86", "ARM", "assembly" | `ctf-reverse` | Análise de binários, disassembly, decompilação, strings, symbols |
| "exploit", "buffer overflow", "ROP", "heap", "shellcode", "format string", "bypass ASLR", "stack", "use-after-free" | `ctf-pwn` | Binary exploitation, desenvolvimento de exploits, pwntools |
| "crypto", "criptografia", "RSA", "AES", "ECC", "decrypt", "hash", "assinatura", "side-channel", "PRNG" | `ctf-crypto` | Criptoanálise, quebra de cifras, ataques a RSA/ECC |
| "js reverso", "AST", "ofuscacao js", "webpack", "wasm reverso", "deobfuscate", "javascript reverse", "JSVMP" | `jsr-reverse` | Reverse engineering de JavaScript/Web, AST, desofuscação, WASM |

### 🔴 Malware Analysis

| Gatilho | Skill | Quando Usar |
|---------|-------|-------------|
| "malware", "triagem", "virus", "ransomware", "trojan", "indicadores", "IOC", "hash", "amostra suspeita" | `malware-triage` | Triagem inicial de malware, extração de IoCs, hashes |
| "sandbox", "análise dinâmica", "comportamento malware", "sysmon", "process monitor", "registry", "network capture" | `malware-dynamic-analysis` | Análise dinâmica de malware, sandbox, bypass anti-análise |
| "detectar", "regra detecção", "YARA", "Sigma", "Suricata", "snort", "hunting", "detection engineering" | `detection-engineer` | Criação de regras de detecção YARA/Sigma/Suricata |
| "relatório malware", "writeup malware", "documentar amostra", "report" | `malware-report-writer` | Geração de relatórios profissionais de malware |
| "analisar arquivo", "formato arquivo", "PDF malicioso", "office macro", "PE analysis", "ELF header" | `specialized-file-analyzer` | Análise de formatos de arquivo específicos |

### 🔴 Segurança Ofensiva & Web

| Gatilho | Skill | Quando Usar |
|---------|-------|-------------|
| "web", "XSS", "SQLi", "CSRF", "SSRF", "SSTI", "IDOR", "command injection", "LFI", "RFI", "XXE" | `ctf-web` | Web exploitation, hacking web, vulnerabilidades web |
| "forense", "forensics", "recuperar dados", "memory dump", "volatility", "stego", "esteganografia", "carving" | `ctf-forensics` | Análise forense digital, recuperação, esteganografia |
| "OSINT", "inteligência", "investigação", "redes sociais", "whois", "dork", "google hacking", "recon" | `ctf-osint` | Inteligência de fontes abertas, investigação digital |
| "pentest", "scan", "nmap", "metasploit", "exploit web", "ffuf", "burp" | `ctf-web` | Pentest web, scanning, fuzzing |

### 🔴 Segurança Defensiva & Auditoria (Trail of Bits)

| Gatilho | Skill | Quando Usar |
|---------|-------|-------------|
| "variante de bug", "encontrar bugs similares", "bug variant", "padrão de vulnerabilidade", "grep vulnerability" | `variant-analysis` | Encontrar variantes de bugs conhecidos no código |
| "regra semgrep", "SAST", "análise estática customizada", "lint security" | `semgrep-rule-creator` | Criar regras Semgrep para análise estática |
| "análise estática", "static analysis", "code scan segurança", "SAST scan" | `static-analysis` | Análise estática de segurança geral |
| "revisar C", "C code review", "buffer overflow C", "use-after-free C", "memory safety" | `c-review` | Code review de segurança para código C/C++ |
| "supply chain", "dependência maliciosa", "cadeia de suprimentos", "package audit", "npm malware", "pip malware" | `supply-chain-risk-auditor` | Auditoria de cadeia de suprimentos de software |
| "regra YARA", "criar YARA", "YARA rule", "pattern matching malware" | `yara-authoring` | Criação de regras YARA para detecção de malware |
| "superfície ataque", "attack surface", "entry point", "endpoint descoberto", "API externa" | `entry-point-analyzer` | Mapear superfície de ataque de uma aplicação |
| "auditar agente AI", "tool use audit", "agent action audit", "prompt injection agent", "agentic safety" | `agentic-actions-auditor` | Auditar ações de agentes AI, prompt injection |
| "timing attack", "side channel", "constant time", "crypto timing", "timing leak" | `constant-time-analysis` | Análise de timing side-channel em código criptográfico |
| "zeroize", "memória segura", "secure memory", "limpar segredo", "cleanup sensitive", "key erasure" | `zeroize-audit` | Verificar limpeza segura de dados sensíveis na memória |

### 🟢 SuperEzio (Projeto Financeiro)

| Gatilho | Skill/Rota | Quando Usar |
|---------|-----------|-------------|
| "investimento", "ticker", "análise financeira", "mercado", "ETF", "dividendos", "carteira" | Pipeline SuperEzio (`src/agent_server/main.py`) | Análise financeira, investimentos, tickers |
| "pipeline", "UniversalPipeline", "gateway", "model serving" | Código fonte em `src/core/` | Questões sobre o pipeline do SuperEzio |
| "endpoint", "API", "/task/submit", "fastapi", "rota" | `src/agent_server/endpoints.py` | Questões sobre a API do SuperEzio |

---

## Fase 3: Tomada de Decisão

### Algoritmo de Confiança

1. **Match de Intent (50%)**: Quão claramente o pedido casa com os padrões?
   - Keyword exata: 1.0
   - Match parcial: 0.6
   - Match inferido: 0.3

2. **Relevância de Contexto (30%)**: O estado atual do projeto é relevante?
   - Muito relevante: 1.0
   - Pouco relevante: 0.5
   - Irrelevante: 0.0

3. **Ambiguidade (20%, invertida)**: Quantas opções viáveis?
   - 1 opção clara: 1.0
   - 2-3 opções: 0.5
   - 4+ opções: 0.0

**Score Final** = (intentMatch × 0.5) + (contextRelevance × 0.3) + ((1 - ambiguity) × 0.2)

**Níveis**:
- **Alto (>0.7)**: Roteia direto, explica brevemente
- **Médio (0.4-0.7)**: Roteia e mostra alternativas
- **Baixo (<0.4)**: Pergunta para clarificar

---

## Fase 4: Execução

### Padrões de Execução

1. **Single Tool**: Uma skill resolve → Invoca direto com `Skill(skill: "nome-da-skill")`
2. **Sequential Chain**: Dependências → Executa em ordem (ex: triar malware → analisar → relatório)
3. **Parallel**: Independentes → Dispara juntas (ex: YARA + análise estática simultâneas)

### Mapeamento de Invocação

- **Skills**: Use `Skill(skill: "nome-da-skill")`
- **Agents**: Use `Agent(subagent_type: "tipo", description: "...", prompt: "...")`
- **Bash direto**: Apenas se nenhuma skill cobre a tarefa

---

## Fase 5: Comunicação

### Templates

**Alta Confiança:**
```
🎯 {skill_name} detectada para: {tarefa}. Executando...
```

**Média Confiança:**
```
🎯 {skill_name} para: {tarefa}
💡 Alternativa: {alt_skill} — {quando_usar}
```

**Baixa Confiança:**
```
🤔 Pode ser: 1) {op1} 2) {op2} 3) {op3}. Qual faz mais sentido?
```

---

## Exemplos Práticos

| Pedido do Marco | Roteamento |
|----------------|------------|
| "reversa esse binário pra mim" | `ctf-reverse` |
| "cria uma regra YARA pra detectar esse ransomware" | `yara-authoring` → chain: `malware-triage` → `detection-engineer` |
| "analisa essa amostra suspeita" | `malware-triage` → `malware-dynamic-analysis` |
| "esse código tem vulnerabilidade?" | `static-analysis` + `semgrep-rule-creator` |
| "quero crackear esse programa" | `ctf-reverse` → `ctf-pwn` |
| "me explica esse esquema de crypto" | `ctf-crypto` |
| "acharam um PDF malicioso no email" | `specialized-file-analyzer` → `malware-triage` |
| "como está o pipeline do SuperEzio?" | Exploração do código fonte |
| "analisa o ticker AAPL" | Pipeline SuperEzio → `src/agent_server/main.py` |
| "faz um pentest nesse site" | `ctf-web` |

---

**Versão**: 2.0.0-mikecode
**Skills Registradas**: 23 (7 CTF + 5 Malware + 10 Trail of Bits + 1 JS RE)
