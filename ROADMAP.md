# SuperEzio Financeiro Roadmap - Bob Core Runtime

Atualizado em 2026-06-29.

## Estado Atual

- Runtime local: API `8002` e Bob Core `8082`.
- Modelo operacional: `bob-core-local.gguf` com `bob-lora-best.gguf`.
- Modo de produto: pesquisa e validacao paper.
- Broker: offline ate a probe real do IBKR/TWS confirmar `port_open=true`.
- GitHub: bloqueado por politica DISK ONLY.

## P0 - Pronto Para Demo Local

- [x] Usar aliases neutros de runtime: `bob-core-local.gguf` e `bob-lora-best.gguf`.
- [x] Remover branding antigo das superficies ativas de runtime, manifest, README, runbooks e contratos.
- [x] Corrigir contrato oficial de runtime para Bob Core.
- [x] Corrigir shim legado `core.pipeline.nodes.collect_experts`.
- [x] Corrigir smoke de browser para a UI atual (`#user-inp`, `msg-ceo`).
- [x] Corrigir botao de chart para chamar `loadChart()` sem passar evento bruto.
- [x] Corrigir `/cockpit/portfolio` e `/health/details` para nao marcar broker como paper conectado quando o snapshot vivo esta offline.
- [ ] Reiniciar API e Bob Core com os aliases neutros e validar `/v1/models`, `/health/details`, chart e chat.
- [ ] Rodar browser smoke completo com chat.

## P1 - Gates De Qualidade

- [x] `python -m ruff check src tests`
- [ ] `python -m pytest tests/contracts/test_contract_runtime_official.py -q -p no:cacheprovider`
- [ ] `python -m pytest tests/test_runtime_smoke.py tests/test_pipeline_smoke.py -q -p no:cacheprovider`
- [ ] `python -m pytest tests -q -p no:cacheprovider --maxfail=10`
- [ ] Corrigir qualquer falha restante de suite completa antes de chamar release local.

## P2 - Broker E Execucao Paper

- [ ] Abrir TWS/IB Gateway paper em `127.0.0.1:7497`.
- [ ] Confirmar `scripts/broker_readiness_probe.py --provider ibkr --json --timeout 5`.
- [ ] So depois disso permitir `paper_order_enabled`.
- [ ] Manter `can_submit_orders=false` quando a probe real falhar.
- [ ] Registrar toda hipotese paper no PaperJournal com estado `research_only` quando broker estiver offline.

## P3 - Treino E Avaliacao

- [ ] Avaliar qualidade da LoRA best com prompts de tool-calling, broker offline e negacoes.
- [ ] Corrigir roteamento de negacao: pedidos como "nao recomende compra" nao podem virar scan de oportunidades.
- [ ] Se rodar novo treino longo, usar checkpoint periodico e registrar hash final.
- [ ] Promover adapter apenas depois de eval de resposta, nao so loss/hash.

## P4 - Limpeza Historica

- [ ] Arquivar ou renomear scripts legados de treino/bench que ainda citam nomes de modelo antigos.
- [ ] Separar whitepapers/carreira/Nitro historicos da documentacao ativa do produto.
- [ ] Manter checkpoints antigos como evidencia, mas fora da rota operacional padrao.
- [ ] Atualizar guias de comprador/setup para Bob Core.

## Criterio De Pronto

O sistema so deve ser chamado de pronto quando:

- API e Bob Core sobem com aliases neutros.
- `/health/details` nao contradiz a probe real do broker.
- Chart renderiza no browser.
- `/task/submit` chega em `STREAM_END` com resposta coerente ao intent.
- Ruff passa.
- Contratos oficiais e smokes focados passam.
- Suite completa nao quebra na coleta.
