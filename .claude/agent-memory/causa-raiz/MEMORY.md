# Memory Index

- [Local brain serving stack](local-brain-serving-stack.md) — :8080 llama-server, clientes :8083/:8002 são HTTP; logs em f51-llamacpp; baselines 40,4 tok/s
- [llama.cpp absorve cudaMalloc OOM](llamacpp-absorve-cuda-oom.md) — falha "de pé e errado": model loaded + 1/40 de velocidade, evidência só no stderr do load
- [paper_journal 100% contaminado](paper-journal-100-por-cento-contaminado.md) — os 534 registros são fila de teste + heartbeats; a remediação preservou-os de propósito
- [Gate do scan insatisfatível](scan-gate-insatisfativel.md) — exige catalyst/risk/invalidation que ninguém produz; 21/21 scans de 14/09 deram 0 candidatos
