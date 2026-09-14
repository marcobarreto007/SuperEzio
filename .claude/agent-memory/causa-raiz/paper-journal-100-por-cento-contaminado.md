---
name: paper-journal-100-por-cento-contaminado
description: Todo o conteúdo de data/paper_journal.jsonl é sintético (fila de teste + heartbeats) — os 534 registros vivos não têm nenhum sinal de produção, e a remediação de 2026-08-19/23 preservou-os de propósito
metadata:
  type: project
---

`data/paper_journal.jsonl` **não contém nenhum sinal de produção**. Verificado por
contagem e por hash em 2026-09-14: os 534 registros são 453 linhas de fixture do
arquivo de teste `tests/contracts/test_mangala_tracker.py` + 81 ordens BLOCKED
gravadas por `tests/test_auto_full_analysis.py` (`run_id=paper-order-history-repair-test`
e `forced-consensus-test`).

Fatos que levam tempo para redescobrir:

- **`MangalaTracker.record_flip` não tem nenhum caller de produção.** O endpoint
  `/cockpit/mangala` (`src/agent_server/endpoints.py:2274`) só LÊ
  (`compound_summary()`). Toda linha `mangala-*` no journal só pode ter vindo do pytest.
- **O journal nunca teve ticker do universo de 108 ETFs.** Nem antes do cleanup: o
  arquivo íntegro pré-limpeza (`runtime/quarantine/paper_journal-before-heartbeat-cleanup-20260819.jsonl`,
  6690 registros) tem 5 tickers distintos — `__HEARTBEAT__` 6156, AAPL 314, PLUG 80,
  MSFT 70, GOOGL 70 — e **zero** dos 108 símbolos de `config/td_direct_commission_free_etfs.json`.
  O universo ETF é *gate de custo* (`is_commission_free` em `execution_policy.py:113`,
  `collector.py:1627`), não fonte de sinais gravados.
- **O arquivo parou de crescer em 2026-08-19.** O sha256 atual
  (`674228a41ae6ed64e1de263a18ea3ff7ffeb4b80cbab2b7f64d0d0ff4bd18e80`) é byte-idêntico ao
  `source_sha256_after` do cleanup de heartbeats daquele dia. Nada escreveu desde então,
  apesar de ~150 processos de pytest.
- **A remediação foi deliberadamente não-destrutiva.** O checkpoint
  `.f51/checkpoints/2026-08-23-casual-greeting-intent-fix.json` registra "quarantine
  proven synthetic records **without deletion**" — é por isso que as 453 linhas de teste
  continuam no journal vivo, selecionadas por `scripts/quarantine_paper_journal.py`
  (que só COPIA: `source_modified: false`).
- **Os artefatos de evidência** estão em `runtime/quarantine/` (3 manifestos + 5 arquivos
  de registros) — é lá que estão os números de antes/depois, não no código.

**Why:** quem olhar o journal sem saber disso vai tratar 534 linhas sintéticas como
histórico de decisão e tirar conclusões sobre a estratégia a partir de literais de teste
(AAPL a 100.1234, AAPL a 150.0, PLUG a 0.0). O disfarce é forte: os campos de tese estão
100% preenchidos e o formato é o schema real.
**How to apply:** ao investigar o journal, comece por `runtime/quarantine/*.manifest.json`
e pelo sha256 do arquivo vivo antes de contar qualquer coisa; desconfie de qualquer
"tese" cujo `entry_price` seja redondo. Ver [[local-brain-serving-stack]].
