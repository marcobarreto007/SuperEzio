# SuperEzio & MIKE — Model Setup

## 1. Cérebro Local (MIKE & Ferramentas Locais / Código)

O modelo local ativo nesta máquina (servido na porta `127.0.0.1:8080` via `llama-server`) é o **Cyber-Tiel-Coder-35B-A3B-MTP-UD-Q3_K_XL**:

- **Arquivo principal**: `C:\Users\marco\models\cyber-tiel-coder-35b-a3b\Cyber-Tiel-Coder-35B-A3B-MTP-UD-Q3_K_XL.gguf` (17.2 GB)
- **Projetor multimodal (visão)**: `C:\Users\marco\models\cyber-tiel-coder-35b-a3b\mmproj-BF16.gguf` (0.9 GB)
- **Finalidade**: Cérebro local dedicado ao MIKE (`:8083`), especializado em geração de código, tool calling e raciocínio técnico.
- **Rollback documentado**: `C:\Users\marco\models\ornith-1.5-35b-a3b\Ornith-1.5-35B-A3B-Q3_K_XL.gguf` (17.8 GB).
- **Script de inicialização**: `C:\Users\marco\f51-llamacpp\start-f51.ps1` (disparado no boot pelo Windows via `start-f51.cmd`).

## 2. SuperEzio (Decisão e Comitê)

- **Bob (CEO / Agente Central)**: `deepseek-v4-pro` (API oficial DeepSeek HTTPS).
- **Orquestrador**: `deepseek-v4-pro`.
- **Especialistas Financeiros (6 roles), Judge e Auditor**: `deepseek-v4-flash` (API oficial DeepSeek HTTPS).
- **Fallback opcional**: `glm-5.3` (Z.ai Coding Plan).

## 3. Modelos Locais Quantitativos / ML do SuperEzio (CPU / Scipy / Sklearn)

- **`TechnicalNeuralExpert`**: MLP tri-classe (UP, DOWN, SIDEWAYS) com calibração out-of-sample contra climatologia de retornos (`src/experts/technical_neural/`).
- **12 Modelos de Crise**: LPPLS, Hawkes Process, Growth-at-Risk, Shiller CAPE, SRISK, Minsky-Keen, Markov Switching, BIS Credit Gap, etc. (`src/experts/crisis/models/`).
- **Meta-Labeling & Triple Barrier**: Calibração probabilística pré-broker e dimensionamento de posição (`src/core/trading/meta_labeling.py`).
- **TF-IDF RAG Forense**: Recuperação vetorial léxica via Scikit-learn (`src/core/rag/tfidf_rag.py`).

## How To Add Variants

Option 1: copy a GGUF from an existing verified SuperEzio installation
into `models\` (project dir) or `%USERPROFILE%\models\qwen3.8-27b\`.

Option 2: download Qwen3.8-27B quants from the official source
(`unsloth/Qwen3.8-27B-GGUF` on Hugging Face) into either path above.

Option 3: point `SUPEREZIO_MODEL_PATH` at any other compatible GGUF.

## Verify

Run the launch script — it fails fast if the model is missing:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\serve_agent_llamacpp.ps1 -Port 8080
```

Expected: the banner prints the model path and the server starts. Any
`ERROR: Model not found` means the file is still absent.

## Packaging Rule

Do not include `*.gguf` files in source-only packages unless explicitly agreed.
