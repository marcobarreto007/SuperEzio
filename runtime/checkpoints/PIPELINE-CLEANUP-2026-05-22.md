# Pipeline cleanup — 2026-05-22

## Plano (concordância)

O plano P0/P1 está alinhado com o estado real do repo: grafo v4 ativo, legado v3 só em `_archive` e contratos.

## Aplicado nesta sessão

| Item | Ação |
|------|------|
| P0-1 `ceo.py` | Já em `src/core/pipeline/nodes/_archive/ceo.py`; testes em `test_contract_ceo.py` importam `_archive` |
| P0 collector import | `adapters.data_collector.subprocess_collector` (corrige `...data_collector.subprocess_collector` inexistente) |
| P0 stub PennyLab | Removido `_node_pennylab_stub` de `graph.py` |
| P1 professional price | Mesh de preço só `hub_price` (DataHub); removidos `twelve_data` / `alpha_vantage` duplicados no mesh |
| `latest.json` | Bloco `runtime_parameters` restaurado (portas 8002/8082, entrypoints, model_path) |
| Docs | `README.md` fluxo v4; `ceo.contract.md` aponta `node_agent` + `_archive` |

## Já estava OK antes

- `nodes/__init__.py` — só exports v4
- `.f51/contracts/pipeline.contract.md` — grafo ReAct v4

## Pendente / decisão do usuário

- **technical_neural**: recomendação = mover para `src/experts/_archive/` ou marcar deprecated; manter só se `DataCollector` legado ainda for obrigatório.
- **pytest**: rodar localmente (ambiente do agente não retornou saída de shell):

```powershell
cd C:\Users\marco\Desktop\SuperEzio
python -m pytest tests/contracts/test_contract_runtime_official.py tests/contracts/test_contract_ceo.py -q
python -m pytest tests/ -q
```

## Verificação esperada

- `test_runtime_checkpoint_tracks_official_entrypoints` — passa com `runtime_parameters` em `latest.json`
- `test_contract_ceo` — passa com imports `_archive.ceo`
