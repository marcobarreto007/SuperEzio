# MARCO BARRETO
**AI Systems & Platform Engineer | Staff AI Engineer**  
📍 São Paulo, Brazil (Available for Remote Work)  
✉️ marcobarreto007@gmail.com | 🔗 [github.com/marcobarreto007](https://github.com/marcobarreto007) | 🔗 [linkedin.com/in/marco-barreto](https://linkedin.com/in/marco-barreto)

---

## 🎯 PROFESSIONAL PROFILE

AI Systems Engineer specializing in **Offline-First** architectures, low-level inference optimization on consumer hardware, and deterministic multi-agent production orchestration. Proven track record of enabling massive LLMs (80B+) in highly resource-constrained environments (16GB VRAM), dramatically reducing cloud costs while maintaining data sovereignty. Expert in hardware-software co-design, Directed Acyclic Graphs (DAGs) for autonomous decision-making systems, and forensic-grade RAG engines.

---

## 🛠️ TECHNICAL SKILLS

- **LLM Optimization & Systems:** llama.cpp, F51 Nitro-MoE (thermal paging protocol), quantization formats (IQ4_XS, GGUF, GPTQ), persistent VRAM expert caching, CUDA Streams, asynchronous Host-to-Device (H2D) PCIe transfers, KV Cache Tiering.
- **Agent Orchestration & Graphs:** LangGraph, LangChain, Pydantic v2 (defensive validation and Zero-Garbage Runtimes), ReAct loop design, adversarial decision DAGs.
- **Computer Vision & Tracking:** YOLO (v8/v9), BoT-SORT, DeepSORT, OpenCV, real-time video stream processing pipelines.
- **Data Engineering & RAG:** ForensicRAG, distributed ETL, financial and market API integrations (Twelve Data, yfinance, Finnhub).
- **Backend & Infrastructure:** Python (performance-optimized), FastAPI, uvicorn, PowerShell/WSL scripting, C/C++ (tensor operator porting), Docker, Git (isolated workflows/custom policies).

---

## 🚀 FEATURED PROJECTS & PORTFOLIO ENGINEERING

### 1. F51 Nitro-MoE — MoE Inference Protocol via Tiered Expert Placement
*Creator & Lead Systems Engineer* | [GitHub Link](https://github.com/marcobarreto007/f51-nitro-moe)
- **Problem:** Running massive MoE models (Qwen3 80B, DeepSeek-Coder-V2 236B) on consumer hardware without hitting severe PCIe bottlenecks or driver GTT memory thrashing.
- **Solution:** Developed a thermal paging protocol that dynamically structures experts across three tiers (GPU VRAM → DDR5 RAM → NVMe SSD) while anchoring attention and routing layers in VRAM.
- **Key Achievements:**
  - Enabled stable execution of **Qwen3 80B at 38.7 tok/s** on a single consumer RTX 5060 Ti 16GB, using only **2.4 GB of VRAM**.
  - Outperformed standard llama.cpp (GPU-all, which collapsed to 8.4 tok/s due to GTT swap thrashing) by **4.6x** and CPU-only mode by **2.3x**.
  - Modeled cold-tier (NVMe) loading patterns for DeepSeek-Coder-V2 (236B) using predictive scheduling under strict time budgets (*slack schedule = 0*).

### 2. SuperEzio Financeiro — Autonomous Multi-Agent Investment Platform
*Lead AI Systems Architect* | [GitHub Link](https://github.com/marcobarreto007/SuperEzio)
- **Problem:** Designing a high-reliability, 100% offline financial advisor immune to mathematical hallucinations with low-latency execution.
- **Solution:** Implemented a LangGraph DAG architecture utilizing pure, isolated decision nodes. Created strict validation schemas using Pydantic v2 and built a custom pre-delivery validation framework (*Zero-Garbage Runtime*) to detect memory leaks and regression anomalies.
- **Key Achievements:**
  - Orchestrated real-time financial decision flows by binding the local CEO LLM (Qwen3 80B Nitro) with deterministic analytical engines (PennyLab & Crisis Engine).
  - Developed a FastAPI gateway featuring Server-Sent Events (SSE) streaming for real-time analysis rendering.
  - Established a 100% green contract and integration test suite (1,100+ tests).

### 3. f51-verdict — Decision Engine with Calibrated Uncertainty & Adversarial Critique
*Lead R&D Engineer*
- **Problem:** Autonomous LLM systems suffer from overconfidence and vulnerability to adversarial inputs or logical pitfalls.
- **Solution:** Constructed a modular decision DAG integrating adversarial critique nodes to stress-test intermediate reasoning before emitting final verdicts.
- **Key Achievements:**
  - Designed the `SpiderSense` module for anomaly and prompt-trap detection, along with the `VeracityGate` for symbolic cross-checking (via WolframAlpha and local solvers).
  - Implemented self-correction loops that calibrate uncertainty metrics dynamically.

### 4. compilai-local — Edge Computer Vision for Low-Latency Traffic Tracking
*Edge & Vision Engineer*
- **Problem:** Counting and tracking vehicles/pedestres continuously on low-power, edge IoT hardware.
- **Solution:** Built an optimized inference pipeline pairing YOLO v8/v9 object detectors with the BoT-SORT multi-object tracking algorithm.
- **Key Achievements:**
  - Streamlined frame-by-frame processing to run in parallel, resolving occlusion issues and eliminating double-counting anomalies.
  - Implemented database persistence and a lightweight local metrics dashboard.

---

## 📈 PROFESSIONAL EXPERIENCE

- **Fuch F51 Labs | Personal AI R&D Laboratory**  
  *Principal AI & Systems Engineer* (2024 - Present)
  - Focused on profiling and optimization of local runtimes (llama.cpp, PyTorch, CUDA) and graph-based cognitive agents.
  - Developed symbolic mathematical reasoning toolkits featuring self-correction and external solver integrations (`nelsonmath`).
  - Authored detailed technical whitepapers highlighting low-level hardware constraints and latency engineering.

---

## 🎓 LANGUAGES & EDUCATION

- **English:** Fluent (Technical reading of academic AI papers, open-source documentation, and technical writing).
- **Portuguese:** Native speaker.
- **Advanced Autodidactism:** Daily study of arXiv papers covering Mixture-of-Experts (MoE) optimizations, low-level CUDA caching, and graph agent patterns.
