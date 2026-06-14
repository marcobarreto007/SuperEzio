# 🖥️ GUIA DE PORTFÓLIO DO GITHUB (Visual & Estrutura)
**Autor:** Marco Barreto | Fuch F51 Labs  

O seu GitHub é o seu maior cartão de visitas. Recrutadores e gestores técnicos de IA não leem apenas currículos; eles abrem o código, olham a organização dos arquivos, o padrão de commits, e a clareza da documentação.

Este guia prático mostra como transformar o seu perfil [github.com/marcobarreto007](https://github.com/marcobarreto007) em uma vitrine de engenharia de IA de nível sênior.

---

## 🎨 1. O SEU README DE PERFIL (A Vitrine Principal)

No GitHub, se você criar um repositório público com o mesmo nome do seu usuário (`marcobarreto007`), o arquivo `README.md` dele aparecerá no topo da sua página de perfil.

Crie o repositório **[marcobarreto007/marcobarreto007](https://github.com/marcobarreto007/marcobarreto007)** e cole o seguinte código:

```markdown
# Olá, eu sou o Marco Barreto! 🚀
**AI Systems & Platform Engineer | Staff AI Engineer**

Sou um desenvolvedor especializado em engenharia de sistemas de inteligência artificial offline-first, otimização de inferência em hardware de consumo (Mixture-of-Experts) e orquestração de agentes cognitivos determinísticos.

---

## 🛠️ Tecnologias & Foco
- **Inference Latency Engineering:** llama.cpp, CUDA Streams, Quantização (GGUF, IQ4_XS), persistent VRAM caching, KV Cache Tiering.
- **Cognitive Agent Architectures:** LangGraph, LangChain, grafos acíclicos (DAGs) de decisão, Pydantic v2 validation.
- **Edge AI & Vision:** YOLO (v8/v9), BoT-SORT object tracking, pipelines de vídeo em tempo real de baixa latência.
- **Data Engineering:** ForensicRAG, ETLs locais de alto desempenho, barramentos de dados.

---

## 🚀 Projetos em Destaque

### 🏎️ [F51 Nitro-MoE](https://github.com/marcobarreto007/f51-nitro-moe)
*Protocolo de Paginação Térmica para Mixture-of-Experts*
- **O que faz:** Viabiliza a execução do **Qwen3 80B a 38.7 tok/s** estável em uma única GPU RTX 5060 Ti de 16GB, consumindo apenas **2.4 GB de VRAM** (um ganho de 4.6x sobre a inferência padrão saturada).
- **Keywords:** llama.cpp, PCIe bottlenecks, Asynchronous Host-to-Device copying, Memory Hierarchies.

### 💼 [SuperEzio Financeiro](https://github.com/marcobarreto007/SuperEzio)
*Agente Autónomo de Assessoria de Investimentos Offline*
- **O que faz:** Orquestra múltiplos agentes e experts locais (PennyLab & Crisis Engine) usando um grafo robusto em LangGraph. Possui validação defensiva rigorosa, barreira contra alucinações matemáticas e arquitetura Zero-Garbage Runtime contra vazamento de memória.
- **Keywords:** LangGraph, Pydantic v2, FastAPI, Playwright (E2E testing), Offline-First.

### 👁️ [compilai-local](https://github.com/marcobarreto007/compilai-local)
*Visão Computacional e Rastreamento de Tráfego Local*
- **O que faz:** Processamento paralelo de vídeo em tempo real usando YOLO e tracking BoT-SORT para contagem inteligente de fluxo de tráfego, eliminando erros comuns de oclusão de objetos.
- **Keywords:** YOLOv8, YOLOv9, BoT-SORT, OpenCV, Edge AI.

---

## 📈 Métricas de Engenharia
- **Filosofia de Software:** Sistemas auditáveis, testes de contrato, 100% offline-first, eficiência máxima por dólar gasto em hardware.
- **Atividade Recente:** P&D ativo em Mixture-of-Experts de alta escala (200B+ parameters) sob restrição extrema de memória.

📫 **Contato:** marcobarreto007@gmail.com | [LinkedIn](https://linkedin.com/in/marco-barreto)
```

---

## 📌 2. REPOSITÓRIOS PINADOS (Pinned Repositories)

O GitHub permite fixar até 6 repositórios na sua página inicial. Pinte estes 4 projetos na seguinte ordem de prioridade:

1. **f51-nitro-moe** (O seu projeto mais chamativo e inovador no momento).
2. **SuperEzio** (Demonstra que você sabe estruturar projetos comerciais complexos, com testes, runbooks e arquitetura corporativa).
3. **f51-verdict** (Mostra profundo conhecimento teórico e conceitual em IA adversarial e grafos de decisão).
4. **compilai-local** (Demonstra versatilidade em visão computacional, processamento de vídeo e IA de borda).

---

## 🧼 3. HIGIENE E APRESENTAÇÃO DOS REPOSITÓRIOS

Para cada um dos repositórios acima, garanta que:

- **A descrição (About) no menu lateral direito esteja preenchida.**
  *Exemplo para o f51-nitro-moe:* "Thermal paging protocol for Mixture-of-Experts (MoE) LLMs. Run Qwen3 80B at 38.7 tok/s on a single consumer RTX 5060 Ti 16GB."
- **As Tags do repositório estejam preenchidas.**
  *Adicione termos como:* `llm-inference`, `mixture-of-experts`, `llama-cpp`, `cuda`, `langgraph`, `ai-agents`.
- **O README seja o primeiro documento a impressionar.**
  - Sempre inclua um bloco de **TL;DR** com números claros (tabelas de performance, porcentagens de otimização).
  - Explique claramente o **problema**, a **arquitetura** e **como rodar** (passo a passo limpo).
  - Adicione a seção "What did NOT work" (assim como você fez no Nitro-MoE). Engenheiros sêniores de outras empresas valorizam muito isso.
