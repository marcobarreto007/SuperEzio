---
name: f51-prop-test
description: "Testes de propriedade com Hypothesis para todos os validadores de input. Gera milhares de casos aleatórios para encontrar edge cases que testes unitários não cobrem. Triggers: property test, hypothesis, fuzzing, edge case, property-based, invariant."
compatibility: "SuperEzio bootstrap layer"
allowed-tools: "Read, Edit, Write, Bash, Grep, Diff"
depends-on: [f51-contracts, f51-tests]
related-skills: [f51-regression-hunter, f51-quality-gate, f51-executor]
---

# f51-prop-test

## Quando usar

- Validadores de input são testados só com casos felizes conhecidos
- Não há garantia de que o validador funciona para qualquer string aleatória
- Regex de parsing (ticker, trade intent) pode ter edge cases não descobertos
- Precisa de confiança estatística de que um validador não quebra

## Nunca fazer

- Rodar property test sem `max_examples` definido (padrão 100 é mínimo)
- Assumir que passar 100 exemplos = provado correto
- Usar Hypothesis em teste de integração (só unitário)
- Deixar property test lento (>1s por exemplo)

## Workflow

1. **Identificar validadores**: regex de ticker, trade intent, price, quantity, formato de data.
2. **Definir propriedades**: "para qualquer string que passe na regex, `is_valid_ticker_format()` retorna True". "para qualquer string que falhe na regex, retorna False".
3. **Escrever estratégias Hypothesis**: `from hypothesis import strategies as st`. Ex: `st.from_regex(r'^[A-Z]{1,5}(\.[A-Z]{1,3})?$')` para tickers válidos.
4. **Rodar com `@given`**: mínimo 1000 exemplos por validador.
5. **Adicionar health check**: `@settings(suppress_health_check=[HealthCheck.too_slow])` se necessário.
6. **Rodar no CI**: `pytest -m property` (marcador dedicado).

## Propriedades universais a testar

| Validador | Propriedade |
|---|---|
| `is_valid_ticker_format(s)` | `∀ s: valid(s) → s matches regex` e `∀ s: not valid(s) → s não quebra o sistema` |
| `is_explicit_trade_intent(t)` | `∀ t contendo "comprar X": trade_intent(t) == True` |
| `is_explicit_trade_intent(t)` | `∀ t contendo "explica": trade_intent(t) == False` |
| `is_ticker_blacklisted(s)` | `∀ s ∈ BLACKLIST: blacklisted(s) == True` e `∀ s ∉ BLACKLIST: blacklisted(s) == False` |
| `resolve_and_validate_ticker(s)` | `∀ s válido: retorna (ticker, price, None)` ou `(None, None, error_code)` |
| `evaluate_trade_gate(...)` | `∀ input: decision.status ∈ {ALLOW, BLOCK, REVIEW}` |

## Entregáveis mínimos

```
== F51 PROP TEST REPORT ==

## Validadores testados
- [função]: [N propriedades] [N exemplos] [edge cases encontrados]

## Edge cases descobertos
- [entrada]: [comportamento esperado vs real] [corrigido?]

## Estratégias Hypothesis
- [nome]: [st.text() / st.from_regex() / st.sampled_from()]

## Cobertura de propriedades
- [validador]: [X/Y propriedades cobertas]

## CI integration
- [pytest -m property]: [PASS / FAIL]

## Checkpoint
- Atualizado em `.f51/checkpoints/latest.json`
```

## Regras

- Property test não substitui unit test — complementa.
- Mínimo 1000 exemplos por validador crítico (ticker, price, trade intent).
- Se Hypothesis encontrar edge case: registrar, corrigir, e adicionar caso ao unit test.
- Nunca commitar property test quebrado "porque é raro".
