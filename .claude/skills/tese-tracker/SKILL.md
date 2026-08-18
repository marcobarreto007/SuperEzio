---
name: tese-tracker
description: Mantém teses de mercado falsificáveis cross-session — scorecard de pilares, invalidação, catalysts e conviction em runtime/theses/<TICKER>.json. Triggers on "tese", "atualizar tese", "a tese ainda vale", "scorecard", "conviction".
---

# Tese Tracker — tese falsificável com estado estruturado

Derivado do `thesis-tracker` oficial da Anthropic (financial-services), adaptado
ao day-trading do SuperEzio. Princípio herdado verbatim do original:

> "A thesis should be falsifiable — if nothing could disprove it, it's not a thesis.
> Track disconfirming evidence as rigorously as confirming evidence."

## Workflow

### Passo 1: Carregar ou criar
- Existe `runtime/theses/<TICKER>.json`? Carregue. Senão, crie a partir do
  relatório mais recente em `runtime/reports/<TICKER>-<data>.md` (não invente
  pilares que não estão no relatório).

### Passo 2: Atualizar pilares com evidência nova
- Para cada pilar: classifique `intacto` | `enfraquecido` | `rompido`
- **Evidência desconfirmante é atualização, não anomalia** — registre-a com o
  mesmo rigor (e a mesma fonte/citação) da confirmante

### Passo 3: Scorecard
- Direção, nº de pilares por status, invalidação (status: `vigente` | `disparada`)
- Conviction 0-10 **com justificativa** — conviction que nunca muda é decoração

### Passo 4: Catalysts
- Eventos esperados com data, impacto esperado e (a posteriori) resultado real
- Catalyst passado sem registro de resultado = dívida de journaling

### Passo 5: Revisão e saída
- Se invalidação `disparada` ou maioria dos pilares `rompido`: marque a tese
  `morta` com data e evidência — **não apague** (histórico é o ativo)
- Grave em `runtime/theses/<TICKER>.json` (formato abaixo)

## Formato do arquivo (contrato)

```json
{
  "ticker": "AAPL",
  "direcao": "long|short|neutro",
  "status": "viva|morta",
  "criada_em": "...", "atualizada_em": "...",
  "pilares": [
    {"claim": "...", "status": "intacto|enfraquecido|rompido",
     "evidencia": "...", "fonte": "...", "ts": "..."}
  ],
  "invalidacao": {"condicao": "...", "preco_evento": 0.0, "status": "vigente|disparada"},
  "conviction": {"score": 0, "justificativa": "...", "historico": [{"ts": "...", "de": 0, "para": 0}]},
  "catalysts": [{"evento": "...", "data_esperada": "...", "ocorreu": null, "resultado_real": null}],
  "revisoes": [{"ts": "...", "mudanca": "...", "evidencia_desconfirmante_considerada": "..."}]
}
```

## Princípios-chave (não-negociáveis)

1. **Falsificabilidade**: pilar sem condição observável de refutação não é pilar
2. **Simetria de evidência**: desconfirmante pesa igual à confirmante
3. **Todo claim cita fonte** — sem fonte, `[SEM FONTE]` e não entra no scorecard
4. **Morte é registrada, nunca apagada**
5. Nenhuma ação de ordem sai daqui — este tracker informa; execução passa pelo
   portão humano (TWO_PHASE_ORDER / money-gate)

## Erros comuns

- Conviction que só sobe (viés de confirmação disfarçado de score)
- Invalidação vaga ("se o mercado piorar") — deve ser preço/evento específico
- Catalyst sem resultado real registrado depois que passou
