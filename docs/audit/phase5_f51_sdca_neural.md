# Fase 5 - F51, SDCA, Neural

Gerado: 2026-07-19
Escopo: src/f51/*.py, src/core/risk_firewall/*.py, src/experts/neural_decision/*.py, src/experts/technical_neural/*.py
Metodo: leitura direta de codigo e validacao local minima

## Achados

### 5.1 - spider_sense com mapeamento inconsistente
- Arquivo: src/f51/graph.py:205
- Arquivo: src/f51/graph.py:206
- Evidencia: NodeResult recebe confidence com tipo incorreto e evidence danger fixo.
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: ALTA

### 5.2 - proxy de confianca com parcela fixa
- Arquivo: src/f51/graph.py:188
- Evidencia: componente constante no calculo do proxy.
- Verdict: CONFIRMED
- Classe: SINTESE
- Severidade: MEDIA

### 5.3 - thresholds/pesos fixos no F51
- Arquivo: src/f51/formulas.py:37
- Arquivo: src/f51/formulas.py:41
- Arquivo: src/f51/formulas.py:148
- Arquivo: src/f51/formulas.py:152
- Arquivo: src/f51/formulas.py:191
- Arquivo: src/f51/gates.py:29
- Arquivo: src/f51/gates.py:70
- Evidencia: pesos e limiares estaticos em pontos centrais de decisao.
- Verdict: CONFIRMED
- Classe: RISCO
- Severidade: MEDIA

### 5.4 - critic fail-open em excecao
- Arquivo: src/f51/gates.py:200
- Arquivo: src/f51/gates.py:201
- Evidencia: erro no critique retorna valido com confianca media.
- Verdict: CONFIRMED
- Classe: FILTRO
- Severidade: ALTA

### 5.5 - SDCA trata "low" como risco alto em _truthy_high
- Arquivo: src/core/risk_firewall/sdca_lite.py:43
- Verdict: CONFIRMED
- Classe: RISCO
- Severidade: MEDIA

### 5.6 - SDCA local/deterministico no escopo auditado
- Arquivo: src/core/risk_firewall/sdca_lite.py:182
- Arquivo: src/core/risk_firewall/sdca_lite.py:433
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: BAIXA

### 5.7 - neural_decision majoritariamente heuristico
- Arquivo: src/experts/neural_decision/neural_decision_expert.py:206
- Arquivo: src/experts/neural_decision/neural_decision_expert.py:220
- Arquivo: src/experts/neural_decision/neural_decision_expert.py:239
- Verdict: CONFIRMED
- Classe: ALPHA
- Severidade: MEDIA

### 5.8 - technical_neural e neural_decision sao distintos
- Arquivo: src/experts/technical_neural/expert/neural_expert.py:20
- Arquivo: src/experts/neural_decision/neural_decision_expert.py:185
- Verdict: CONFIRMED
- Classe: INFRAESTRUTURA
- Severidade: BAIXA

## Resumo executivo

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| spider_sense inconsistente | INFRAESTRUTURA | ALTA | CONFIRMED |
| critic fail-open | FILTRO | ALTA | CONFIRMED |
| thresholds fixos F51 | RISCO | MEDIA | CONFIRMED |
| SDCA _truthy_high | RISCO | MEDIA | CONFIRMED |
| neural heuristico | ALPHA | MEDIA | CONFIRMED |

## Proximo passo
1. Confirmar com testes focados F51/SDCA/neural.
2. Aplicar patch pontual em spider_sense e revalidar.
