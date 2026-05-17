# F51 Risk Register — SuperEzio

> Atualizado: 2026-05-17 | Sessao: f51-inventory | Branch: main

## Riscos Ativos

### R1 — Config Stale (HIGH)
- **O que:** `config/model_manifest.json` referencia Gemma-4-26B. `config/runtime.yml` nao tem CEO local.
- **Impacto:** Gateway pode tentar inicializar com modelo errado se ler esses arquivos.
- **Mitigacao:** Atualizar ambos para Qwen3.6-35B F51.
- **Urgencia:** Baixa — o `.env` e o script `serve_ceo_llamacpp.ps1` sao a fonte real. Configs parecem nao ser lidos em runtime.

### R2 — VeracityGate Triplicado (MEDIUM)
- **O que:** 3 implementacoes: `src/f51/gates.py`, `src/core/investor/veracity_gate.py`, `src/experts/pennylab/experts/veracity_gate.py`.
- **Impacto:** Mudanca na canonica pode nao ser replicada. Comportamento divergente entre modulos.
- **Mitigacao:** Consolidar no canonico (`src/f51/gates.py`), redirecionar os outros.

### R3 — prompts/gemma.py Shim (LOW)
- **O que:** `src/core/pipeline/prompts/gemma.py` define `GEMMA_SYSTEM_PROMPT = QWEN_SYSTEM_PROMPT`.
- **Impacto:** Codigo que referencia GEMMA ainda funciona, mas e confuso.
- **Mitigacao:** Remover shim quando referencias a GEMMA forem limpas do pipeline.

### R4 — core/trading/ Desconectado (MEDIUM)
- **O que:** `src/core/trading/` (10 modulos: broker, kill_switch, order_builder, RL...) nao esta integrado ao pipeline principal.
- **Impacto:** Codigo mantido mas nao exercitado. Pode apodrecer.
- **Mitigacao:** Conectar ao pipeline ou arquivar como experimental.

### R5 — technical_neural Desconectado (LOW)
- **O que:** `src/experts/technical_neural/` (torch_mlp.py, neural_expert.py) nao integrado ao pipeline.
- **Impacto:** Codigo morto funcional.
- **Mitigacao:** Integrar ao pipeline ou arquivar.

### R6 — Archive com Codigo Vivo (LOW)
- **O que:** `archive/deprecated/` e `archive/quarantine/` contem SpiderSense e EpisodeMemory antigos.
- **Impacto:** Nenhum — nao sao importados. Mas ocupam espaco e confundem.
- **Mitigacao:** Nenhuma necessaria. Archive e seguro.

### R7 — .env com API Keys no Disco (HIGH)
- **O que:** `.env` contem 12+ API keys em plaintext.
- **Impacto:** Se o arquivo vazar (git, backup, screen share), todas as keys sao comprometidas.
- **Mitigacao:** `.env` esta no `.gitignore`. Verificar se `.env.example` nao tem secrets.

## Riscos Mitigados

- ~~Branch paralela `f51/reclamation-runtime`~~ — Deletada 2026-05-17.
- ~~Modelos velhos (Gemma 31B, Qwen3.6-27B)~~ — Movidos para `Desktop/modelos antigos/`.
- ~~GGUF sem MTP~~ — SHA256 confirmado: GGUF novo com tensores MTP.
