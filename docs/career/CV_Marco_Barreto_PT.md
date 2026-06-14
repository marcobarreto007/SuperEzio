# MARCO BARRETO
**AI Systems & Platform Engineer | Staff AI Engineer**  
📍 São Paulo, SP (Disponível para remoto)  
✉️ marcobarreto007@gmail.com | 🔗 [github.com/marcobarreto007](https://github.com/marcobarreto007) | 🔗 [linkedin.com/in/marco-barreto](https://linkedin.com/in/marco-barreto)

---

## 🎯 PERFIL PROFISSIONAL

Engenheiro de Sistemas de IA especializado em arquiteturas **Offline-First**, otimização de inferência de baixo nível em hardware de consumo, e orquestração de múltiplos agentes determinísticos em produção. Histórico comprovado de viabilização de LLMs de grande porte (80B+) em ambientes com restrição severa de recursos (16GB VRAM), reduzindo custos de nuvem e garantindo soberania de dados. Especialista em co-design hardware-software, grafos acíclicos direcionados (DAGs) para sistemas de decisão autônomos, e engines RAG de alta fidelidade forense.

---

## 🛠️ HABILIDADES TÉCNICAS

- **Sistemas & Otimização de LLMs:** llama.cpp, F51 Nitro-MoE (protocolo de paginação térmica), quantização (IQ4_XS, GGUF, GPTQ), buffers persistentes de VRAM, CUDA Streams, transferência assíncrona PCIe (H2D), KV Cache Tiering.
- **Arquitetura de Agentes & Grafos:** LangGraph, LangChain, Pydantic v2 (validação defensiva e Zero-Garbage Runtime), ReAct, DAGs de decisão adversarial.
- **Visão Computacional & Tracking:** YOLO (v8/v9), BoT-SORT, DeepSORT, OpenCV, pipelines de processamento de vídeo em tempo real.
- **Engenharia de Dados & RAG:** ForensicRAG, ETL distribuído, integrações de APIs financeiras e de mercado (Twelve Data, yfinance, Finnhub).
- **Backend & Infraestrutura:** Python (desempenho otimizado), FastAPI, uvicorn, PowerShell/WSL, C/C++ (portabilidade de operadores de tensores), Docker, Git (modo disk-only/políticas de isolamento).

---

## 🚀 PROJETOS DE DESTAQUE & ENGENHARIA DE PORTFÓLIO

### 1. F51 Nitro-MoE — Protocolo de Inferência MoE sob Restrição de Hardware
*Criador & Engenheiro de Sistemas* | [GitHub Link](https://github.com/marcobarreto007/f51-nitro-moe)
- **Problema:** Rodar modelos MoE massivos (Qwen3 80B, DeepSeek-Coder-V2 236B) em hardware de consumo sem sofrer gargalo severo de barramento PCIe ou paginação lenta de VRAM para RAM.
- **Solução:** Desenvolvi um protocolo de paginação térmica de experts (VRAM → DDR5 RAM → NVMe SSD), mantendo apenas as camadas de atenção e roteamento fixadas na GPU.
- **Resultados:**
  - Viabilizou a execução do **Qwen3 80B a 38.7 tok/s** em uma única GPU RTX 5060 Ti de 16GB, utilizando apenas **2.4 GB de VRAM** de forma estável.
  - Superou em **4.6x** o modo padrão do llama.cpp (GPU-all, que colapsou para 8.4 tok/s por paginação do driver GTT) e em **2.3x** o modo apenas CPU.
  - Implementou e simulou o modelo de escalabilidade para o DeepSeek-Coder-V2 (236B), desenhando técnicas de pré-busca baseadas em folga temporal (*slack schedule = 0*).

### 2. SuperEzio Financeiro — Plataforma Multi-Agente Autónoma de Investimentos
*Lead AI Systems Architect* | [GitHub Link](https://github.com/marcobarreto007/SuperEzio)
- **Problema:** Criar um assessor financeiro de alta confiabilidade, 100% offline-first, imune a alucinações matemáticas e com latência de resposta otimizada.
- **Solução:** Desenhei e implementei um pipeline em LangGraph baseado em grafos acíclicos com nós puros e isolados do LLM. Criei um módulo de validação estrita baseada em Pydantic v2 e um validador de memória (*Zero-Garbage Runtime*) que impede vazamentos durante execuções longas.
- **Resultados:**
  - Orquestrou a tomada de decisão financeira unindo o motor CEO local (Qwen3 80B Nitro) com experts deterministicos regionais de mercado (PennyLab & Crisis Engine).
  - Desenvolveu um gateway em FastAPI com suporte a Server-Sent Events (SSE) para streaming em tempo real das análises.
  - Cobertura de testes automatizados determinísticos robusta, com 100% de passagem em testes de contrato e integração.

### 3. f51-verdict — Motor de Decisão com Incerteza Calibrada e Crítica Adversarial
*Engenheiro de P&D (R&D)*
- **Problema:** Decisões autônomas de LLMs sofrem de excesso de confiança (overconfidence) e vulnerabilidade a inputs maliciosos/ambíguos.
- **Solução:** Desenvolvi um motor modular de decisão baseado em DAG que insere nós de crítica adversarial no processo de raciocínio.
- **Resultados:**
  - Implementou o módulo `SpiderSense` para detecção de anomalias/armadilhas nos prompts e o `VeracityGate` para checagem cruzada simbólica (via integrações WolframAlpha e solvers locais).
  - Criou pipelines de refinamento por autocrítica iterativa, calibrando o nível de certeza antes da saída final do sistema.

### 4. compilai-local — Visão Computacional de Baixa Latência aplicada a Tráfego
*Desenvolvedor de Visão Computacional & IoT*
- **Problema:** Rastreamento e contagem contínua de fluxo de objetos (veículos/pedestres) em setups locais de baixo custo energético.
- **Solução:** Integrei o modelo de detecção de objetos YOLOv8/v9 com o algoritmo de rastreamento BoT-SORT.
- **Resultados:**
  - Otimizou o pipeline de processamento frame-a-frame para rodar localmente com processamento paralelo de vídeo, eliminando duplicações causadas por oclusão de objetos.
  - Desenhou o dashboard local e a persistência compacta de estatísticas de tráfego.

---

## 📈 EXPERIÊNCIA OPERACIONAL & MARCOS

- **Fuch F51 Labs | Laboratório de P&D Pessoal**  
  *Engenheiro de IA & Fundador* (2024 - Presente)
  - Foco em otimização de runtimes locais (Llama.cpp, PyTorch, CUDA) e orquestração de sistemas cognitivos baseados em grafos de decisão.
  - Criação de bibliotecas experimentais de raciocínio lógico-matemático de alta fidelidade (`nelsonmath`).
  - Escrita de whitepapers técnicos avaliados positivamente por comunidades como r/LocalLLaMA e Hacker News.

---

## 🎓 INFORMAÇÃO ACADÊMICA & IDIOMAS

- **Inglês:** Fluente (Leitura técnica de whitepapers acadêmicos de IA, documentação de repositórios open-source e escrita científica).
- **Português:** Nativo.
- **Autodidatismo Avançado:** Leitura diária de papers do arXiv (foco em Mixture-of-Experts, otimização de CUDA, e frameworks de orquestração multi-agente).
