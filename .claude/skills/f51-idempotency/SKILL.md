---
name: f51-idempotency
description: "Implementa idempotency key persistente, deduplicação cross-process e dead letter queue para ordens que falham journal. Triggers: idempotency, dedup, duplicata, idempotent, dead letter, journal, ordem duplicada."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts, f51-money-gate]
related-skills: [f51-executor, f51-circuit-breaker, f51-audit]
---

# f51-idempotency

## Quando usar

- Dedup atual é volátil (`deque(maxlen=32)` em memória)
- Reiniciou o processo → perdeu o dedup → ordem duplicada
- Journal falha na escrita e a ordem é descartada sem rastro
- Não existe dead letter queue para ordens que não conseguiram persistir
- Precisa garantir que a mesma ordem nunca é submetida 2x

## Nunca fazer

- Usar só memória para dedup (volátil)
- Usar `run_id` como única chave de idempotência (não sobrevive a retry)
- Descartar ordem silenciosamente sem dead letter
- Implementar idempotency sem testar cenário de crash + restart

## Workflow

1. **Auditar fluxo atual**: mapear todos os pontos onde uma ordem pode ser submetida (`auto_execute_paper.py`, `tool_executor.py`).
2. **Criar idempotency key determinística**: `sha256(ticker + qty + limit_price + timestamp_truncado_5min + account)`. Isso garante que a mesma intenção gera a mesma key mesmo em retry.
3. **Persistir no journal**: antes de submeter, verificar se a idempotency key já existe no journal. Se existir com status `submitted` ou `filled` → pular.
4. **Implementar dedup cross-process**: usar arquivo de lock no journal directory ou tabela SQLite local.
5. **Criar dead letter queue**: `journal/dead_letter/` — ordens que falharam journal write são salvas como JSON para replay manual.
6. **Adicionar reconciliação**: job que verifica `dead_letter/` e tenta reprocessar com backoff.
7. **Testar**: crash simulado no meio da submissão → restart → mesma ordem não duplica.

## Portões de decisão

- Se idempotency key não é determinística: bloqueado.
- Se dead letter queue não tem mecanismo de replay: risco documentado.
- Se dedup cross-process não funciona após `kill -9`: bloqueado.

## Entregáveis mínimos

```
== F51 IDEMPOTENCY REPORT ==

## Fluxo atual (before)
- Dedup: deque(maxlen=32) em memória
- Persistência: nenhuma
- Dead letter: nenhuma

## Fluxo novo (after)
- Idempotency key: sha256(ticker|qty|price|window_5min|account)
- Dedup: verificação no journal antes de submeter
- Dead letter: journal/dead_letter/{timestamp}_{ticker}.json
- Replay: script de reconciliação manual/agendado

## Arquivos alterados
- [lista com diff]

## Testes
- [test_idempotency_cross_restart]: [PASS / FAIL]
- [test_dead_letter_written_on_journal_failure]: [PASS / FAIL]

## Riscos remanescentes
- [se houver]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Idempotency key é determinística e imutável.
- Dedup em memória é cache, não fonte de verdade.
- Toda ordem bloqueada ou falha vai pro dead letter.
- Dead letter sem replay documentado é dívida operacional.
