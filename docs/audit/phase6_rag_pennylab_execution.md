# Fase 6 - RAG, PennyLab, Execucao/Broker

Gerado: 2026-07-19
Escopo: src/core/rag/*.py, src/experts/pennylab/*.py, src/core/trading/*.py, src/adapters/*.py
Metodo: leitura direta de codigo e verificacao de trilhas de execucao

## Achados

### 6.1 - gate central sem enforce explicito de SUPEREZIO_RESEARCH_PAPER_ONLY e SUPEREZIO_LIVE_TRADING_DISABLED
- Arquivo: src/core/pipeline/f51_trade_gate.py:35
- Arquivo: src/core/pipeline/f51_trade_gate.py:39
- Arquivo: src/core/pipeline/f51_trade_gate.py:367
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: CRITICA

### 6.2 - script raw IBKR usa gates paralelos e ignora SUPEREZIO_*
- Arquivo: scripts/_ibkr_order.py:37
- Arquivo: scripts/_ibkr_order.py:58
- Verdict: CONFIRMED
- Classe: RISCO
- Severidade: CRITICA

### 6.3 - live engine carrega paper_only mas sem bloqueio explicito antes de submit
- Arquivo: src/core/trading/trading_engine_live.py:90
- Arquivo: src/core/trading/trading_engine_live.py:469
- Arquivo: src/core/trading/trading_engine_live.py:634
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: ALTA

### 6.4 - fechamento de posicao com submit direto na rotina
- Arquivo: src/core/trading/trading_engine_live.py:614
- Arquivo: src/core/trading/trading_engine_live.py:634
- Verdict: CONFIRMED
- Classe: RISCO
- Severidade: ALTA

### 6.5 - adapter IBKR fail-closed por metadata/freeze
- Arquivo: src/adapters/broker/ibkr_adapter.py:37
- Arquivo: src/adapters/broker/ibkr_adapter.py:90
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: MEDIA

### 6.6 - RAG degrada para vazio/keyword sem erro forte
- Arquivo: src/core/rag/engine.py:193
- Arquivo: src/core/rag/engine.py:236
- Arquivo: src/core/rag/fraud_rag.py:168
- Verdict: CONFIRMED
- Classe: EVIDENCIA
- Severidade: MEDIA

### 6.7 - PennyLab e laboratorio deterministico, sem execucao de ordens
- Arquivo: src/experts/pennylab/config.py:28
- Arquivo: src/experts/pennylab/scoring.py:141
- Arquivo: src/experts/pennylab/cli.py:175
- Verdict: CONFIRMED
- Classe: SINTESE
- Severidade: BAIXA

## Resumo executivo

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| gate central sem enforce SUPEREZIO_* | INFRAESTRUTURA | CRITICA | CONFIRMED |
| script raw sem SUPEREZIO_* | RISCO | CRITICA | CONFIRMED |
| submit sem bloqueio explicito paper_only | INFRAESTRUTURA | ALTA | CONFIRMED |
| RAG fallback vazio/keyword | EVIDENCIA | MEDIA | CONFIRMED |
| PennyLab sem execucao real | SINTESE | BAIXA | CONFIRMED |

## Proximo passo
1. Unificar enforce dos gates SUPEREZIO_* no gate central e bordas de broker.
2. Adicionar bloqueio local explicito no live engine antes de submit.
