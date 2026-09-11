# SuperEzio — Arquitetura-alvo (autoridade invertida)

> Contrato de 2026-09-11. O runtime **ainda** corre o grafo legado
> (`orchestrator_primary` → `auto_full_analysis` → `trinity` → `agent`).
> Cortes **C1** e **C2** estão ligados em sombra: cada run grava
> `evidence_pack.json` e `snapshot.json` com checksum. Nenhum dos dois
> muda decisão, grounding nem paper. Bob **não** lê o snapshot (isso é C3).
> Rollback: `SUPEREZIO_ARCH_C1=0` e/ou `SUPEREZIO_ARCH_C2=0`.

## Invariantes (não negociáveis)

- DISK ONLY. Sem GitHub, sem banco na nuvem.
- Live frozen por default. Paper só com flag explícita.
- LLM não bypassa órgão determinístico. Órgão que importa é **aresta**, não parágrafo.
- Nenhum número na boca do Bob sem provenance no Snapshot (a partir de C3).
- Evidência checksumada. Tese só grava texto BOUND.
- Sem dependência nova para esta arquitetura (stdlib `hashlib` + pydantic já no lock).

## Por que o grafo atual impede 10/10

1. `guardrail_hub` produz prosa; `graph.py` não tem `add_conditional_edges` sobre os 30 checks.
2. `CENSORSHIP_SKIPPED` em `agent.py` quando “há dado” — grounding invertido.
3. `auto_full_analysis` é mega-nó: falha de dado vira string em `errors[]` e o turno segue.
4. Orchestrator é passthrough com `intent_confidence=1.0`.
5. Seis experts + Trinity = um DeepSeek. Consenso de correlação ~1.
6. `macro_observations` só é lido (`f51.py`, `math_hub.py`); ninguém escreve.
7. Tools do Bob recomputam órgãos que o mega-nó já rodou (dual-path).
8. `save_evidence` é best-effort, sem digest canônico, sem ThesisRecord.

## Grafo alvo

```
START → intake
intake  → evidence
evidence → respond_insufficient     [pack.status == INSUFFICIENT]
evidence → snapshot                 [COMPLETE | PARTIAL]
snapshot → organ.math | crisis | f51 | sdca | neural | scan | fraud
organ.* → board
board   → respond_blocked           [BLOCK]
board   → narrator                  [ALLOW | REVIEW]
narrator → evidence                 [pedido de FATO, máx. 2 voltas]
narrator → bind
bind    → persist                   [BOUND | REPAIRED]
bind    → respond_determinist       [REJECTED] → persist
persist → execute_paper             [thesis OPEN + ticket concedido]
persist → END
execute_paper → END
```

Narrator é o **único** LLM da rota de análise. Não calcula número, não decide gate, não pede veredito.

## Contratos

| Contrato | Writer | Fail-closed |
|---|---|---|
| EvidencePack | `evidence` | INSUFFICIENT (fato required faltando) → sem snapshot, sem Bob |
| Snapshot | `snapshot` | imutável; número falado só se existir com provenance |
| OrganVerdict | `organ.<id>` | ERROR nunca vira ALLOW; ABSTAIN visível |
| BindResult | `bind` | NUMBER/GATE sem ref → REJECTED → render determinístico |
| ThesisRecord | `persist` | sem bind BOUND não grava; sem invalidação checável não executa |

Pacote C1 (`src/core/evidence/pack.py`, `pack_builder.py`):

- `facts[key].status`: OK | STALE | MISSING | ERROR
- `coverage.missing` para fatos **required** da rota
- `integrity.canonical_json_sha256` sobre o pack **sem** `integrity`, `created_at` e `facts.*.as_of`
- ticker_analysis required: `price`, `ohlcv`
- `macro_observations` é pedido mas **não** required em C1 (mede buraco; não muda o turno)
- rota `general`/casual sem required → `status=COMPLETE` mesmo com optionals MISSING

Pacote C2 (`src/core/evidence/snapshot.py`):

- `frozen: true`; `numbers[name]` com `value`, `unit`, `formula_id`, `provenance[]`, `computed_by`
- `pack_sha256` liga o snapshot ao EvidencePack
- `as_of` gravado, excluído do hash
- escrito em `runs/evidence/{run_id}/snapshot.json` e em `state.snapshot` no fim de `auto_full_analysis`
- `format_snapshot_binding()` existe para C3; `observation_builder` **não** chama

## O que some (cortes C5–C6, não agora)

- `nodes/trinity.py`
- fan-out de `nodes/experts.py` como “comitê”
- mega-nó inline em `graph.py`
- `orchestrator.py` passthrough
- os `CENSORSHIP_SKIPPED` em `agent.py`
- tools `collect_data` / `f51_firewall` / `run_experts` / `neural_decision` / `sdca_firewall` / `rag_forensics` / `market_scan` como recomputação
- providers órfãos (Stooq, Form4, AlphaSMO, Wolfram)

## O que permanece

DataHub vivo, MathHub/indicadores, 12 modelos scipy de crise, F51, SDCA, neural skill-gate, PennyLab, Mangala, ib_insync, 10 gates, journal, idempotency, atomic write, gateway DeepSeek.

## Migração

| Corte | Flag | Estado 2026-09-11 |
|---|---|---|
| C1 Evidence sombra | `SUPEREZIO_ARCH_C1` default **1** | **ligado** |
| C2 Snapshot congelado | `SUPEREZIO_ARCH_C2` default **1** | **ligado (sombra; Bob não lê)** |
| C3 Bind observe→enforce | `SUPEREZIO_ARCH_C3` | não |
| C4 Órgãos com aresta | `SUPEREZIO_ARCH_C4` | não |
| C5 Dual-path morto | `SUPEREZIO_ARCH_C5` | não |
| C6 Persist+Execute por thesis_id | `SUPEREZIO_ARCH_C6` | não |

Mega-nó só morre no C6. Cada corte é reversível por flag. Sem big-bang.

## NÃO FAÇA

- Melhorar o mega-nó por dentro e chamar isso de arquitetura nova.
- Grounding por regex no texto.
- Deixar um `CENSORSHIP_SKIPPED` “só neste caso”.
- Vender 6 prompts no mesmo modelo como comitê.
- `except Exception` em órgão virando ALLOW.
- Devolver ao LLM a tool de recomputar veredito.
- Persistir prosa crua como tese.
- Live, SaaS, mais provider, mais LLM.

## C1 — o que o código faz agora

`PipelineApp.stream_events` acumula o state dos updates do LangGraph (errors concatenam, não last-write-wins) e, ao finalizar o `EvidenceRun`, grava `runs/evidence/{run_id}/evidence_pack.json` (atomic replace). Bob não lê o arquivo. Decisão, tools e paper permanecem iguais.

## C2 — o que o código faz agora

No fim de `auto_full_analysis` (depois de MathHub e F51), o runtime congela `state.snapshot` a partir do pack + `math_report.numbers`. No finalize, grava `snapshot.json` ao lado do pack. Consumidores do prompt **não** mudam. C3 é quem vai exigir que todo número na boca do Bob exista em `snapshot.numbers`.
