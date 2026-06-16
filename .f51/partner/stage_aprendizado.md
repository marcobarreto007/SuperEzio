# FIX: Aprendizado 6→10/10 — Fechar o ciclo

O FeedbackLoop existe. Extrai lições. Injeta no Bob. Mas o Bob IGNORA.
4 correções pra fechar o ciclo de verdade.

---

## 1. Bob AGE baseado nas lições — tool_executor bloqueia reincidência

**Arquivo:** `src/core/pipeline/nodes/tool_executor.py`

Antes de executar `submit_paper_order`, verificar no FeedbackLoop:
- Este ticker já foi operado antes?
- Qual foi o resultado? (win/loss)
- A tese é similar a alguma que falhou?

Se SIM → BLOQUEAR com mensagem: 
"FeedbackLoop: mesma tese que SNDL em 2026-06-13 resultou em -$200. Reveja."

```python
# Dentro de submit_paper_order, ANTES de enviar pro IBKR:
from core.trading.feedback_loop import get_feedback_loop
feedback = get_feedback_loop()
ticker = args.get("ticker", "")
message = state.get("message", "")
block_reason = feedback.check_before_trade(ticker, message)
if block_reason:
    return {"submit_paper_order_error": f"feedback_loop_blocked:{block_reason}"}
```

Método novo no `FeedbackLoop`:
```python
def check_before_trade(self, ticker: str, thesis: str) -> str | None:
    """Verifica se este trade é similar a algum que falhou. Retorna motivo ou None."""
    # 1. Buscar trades anteriores deste ticker
    # 2. Se houve loss, verificar se a tese é similar
    # 3. Se similar → retornar o motivo do bloqueio
    # 4. Se não → None (permite)
```

---

## 2. Calibragem de confiança — confidence vs outcome

**Arquivo:** `src/core/trading/feedback_loop.py`

Adicionar método:
```python
def calibrate_confidence(self) -> dict:
    """Compara confidence declarada vs outcome real.
    Retorna fator de calibragem: se Bob diz 72 e ganha 46%,
    fator = 0.64 (multiplicar confidence por 0.64).
    """
```

O fator de calibragem é injetado no SYSTEM STATUS:
```
FEEDBACK: 13 trades, 6W/7L (46%), fator calibragem=0.64
```

E o Bob vê: "Sua confiança declarada é 1.56x maior que a real. Ajuste."

---

## 3. bias_report funcionando — preencher confidence nos trades

**Arquivo:** `src/core/pipeline/graph.py` (auto_execute_paper)

Quando registrar trade no PaperJournal, SEMPRE incluir:
```python
{
    "confidence": bob_confidence,  # extraído do final_answer do Bob
    "verdict": bob_verdict,
    "thesis": bob_thesis,
}
```

O código já tenta extrair mas falha (`missing_confidence_data`).
Consertar a extração: pegar do campo `confidence` do `final_answer` do Bob.

---

## 4. Lição → Bloqueio automático no tool_executor

**Arquivo:** `src/core/pipeline/nodes/tool_executor.py`

Ao carregar as lições no startup, registrar padrões de bloqueio:
```python
BLOCKED_PATTERNS = [
    {"ticker": "SNDL", "reason": "rumor nao verificado", "result": "-$200"},
    {"ticker": "GNUS", "reason": "oversold sem fundamento", "result": "-$150"},
]
```

Se Bob tentar `submit_paper_order` com ticker + tese que bate ≥80% similaridade com um padrão bloqueado → BLOQUEAR.

---

## Ordem: 3 → 1 → 2 → 4

Commite depois de cada. Testa antes.

— Deep
