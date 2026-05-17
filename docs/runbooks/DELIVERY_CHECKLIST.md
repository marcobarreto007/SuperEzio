# DELIVERY CHECKLIST — SuperEzio v4.4.0
**Date:** 2026-05-16T23:53:00-04:00

## 🟢 Bloqueadores Mitigados (P0)
- [x] **B01** `main.py:116` — `pipeline.shutdown()` crash. CompiledStateGraph envolto de forma segura na classe `PipelineApp`.
- [x] **B02** `runtime.py` removido — API pública (`chat_async`, `stream_events`, `get_status`) exposta com sucesso na classe `PipelineApp`.
- [x] **B03** Nodes standalone com DI completa — Dependências injetadas corretamente no `build_graph()` e propagadas aos nós.

---

## 🚀 Checklist Pré-Demo (Passo-a-passo)
- [x] Rodar `python -m pytest tests/ -q` e garantir 464 testes passando sem erros.
- [x] Subir o servidor FastAPI localmente usando `python -m agent_server.main`.
- [x] Testar a conectividade básica acessando GET `http://127.0.0.1:8002/health`.
- [x] Testar a integridade profunda do sistema acessando GET `http://127.0.0.1:8002/health/details`.
- [x] Encerrar o servidor com `Ctrl+C` e certificar-se de que o log indica shutdown limpo, sem `AttributeError` ou quebras.

---

## 🟡 Checklist Pré-Venda (Requisitos para Comercialização)
- [ ] Criar `.env.example` centralizando e documentando as 55 variáveis de ambiente mapeadas.
- [x] Adicionar smoke test de ponta a ponta para o `PipelineApp` (testado e ativo em `test_pipeline_smoke.py`).
- [ ] Consolidar imports de `core/engine/` para `core/math/` no roteador FastAPI para remover dependências legadas.
- [ ] Excluir os 3 diretórios vazios (`scanner/`, `mathcore/`, `evidence/`) e o script órfão (`scripts/server.py`).

---

## ⚙️ Checklist Pós-Venda (Manutenibilidade & Backlog)
- [ ] Consolidar prompts do CEO removendo `ceo_prompts.py` em favor do `builder.py`.
- [ ] Mesclar lógica dos nós no pipeline removendo a classe `_mixin.py` de forma definitiva.
- [ ] Ampliar a cobertura de testes para a pasta `investor/` e `observability/`.
