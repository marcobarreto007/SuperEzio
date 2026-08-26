# Stage 5 — Debut: Paper Trading Real + 8 Critérios

O sistema tá pronto. MathHub, 30 guardrails, Trinity, Sentimento Vivo, Cockpit.
Agora precisa OPERAR. Paper trading real com KillSwitch, ApprovalGate, PositionSizer.

---

## Tarefa 1: KillSwitch — integrar no pipeline

**Arquivo:** `src/core/trading/kill_switch.py` (já existe, 127 linhas)

O KillSwitch existe mas NUNCA é chamado. Integrar:

```python
# No graph.py, ANTES de submit_paper_order:
from core.trading.kill_switch import KillSwitch

kill = get_kill_switch()
if kill.is_active:
    return {"blocked": True, "reason": kill.state.reason.value}
```

- Verificar ANTES de cada paper order
- Se ativo → bloquear, logar, notificar no stream
- Se inativo → permitir
- Reset diário automático (meia-noite UTC)

---

## Tarefa 2: ApprovalGate — integrar no pipeline

**Arquivo:** `src/core/trading/approval_gate.py` (já existe, 130 linhas)

- Paper order com risco > $200 → PENDING (aguarda aprovação)
- Paper order com risco <= $200 → auto-approve
- Expor estado no endpoint: `GET /cockpit/summary` já tem `bob.portfolio`
- Adicionar endpoint: `POST /paper/approve/{request_id}` e `POST /paper/reject/{request_id}`

---

## Tarefa 3: PositionSizer — integrar no pipeline

**Arquivo:** `src/core/trading/position_sizer.py` (já existe)

- Max 10% equity por posição
- Max 2% risco por trade
- Calcular tamanho ANTES de submit_paper_order
- Se exceder → cap no máximo e logar warning

---

## Tarefa 4: Ciclo Diário de Paper Trading

**Arquivo:** `src/core/trading/daily_cycle.py`

```python
class DailyCycle:
    """Orquestra o ciclo diário de paper trading."""
    
    async def morning_routine(self):
        """09:00 — Bob acorda, checa Genie (sentimento overnight), checa IBKR."""
        ...
    
    async def trading_session(self, message: str):
        """Marco pergunta → pipeline completo → paper order (se aplicável)."""
        ...
    
    async def evening_routine(self):
        """23:00 — Post-mortem: o que foi certo, o que foi errado, lessons learned."""
        ...
```

---

## Tarefa 5: Fechar C6 — Track Result

**Critério C6**: "Revisit past theses and compare expectation with reality."

- PaperJournal já existe. Popular com trades reais.
- Após 14 dias, comparar: thesis vs outcome.
- Post-mortem automatizado: entry_price vs exit_price, thesis vs reality.
- Registrar no `conversation_memory.jsonl` como `thesis_closed`.

---

## Tarefa 6: Fechar C7 — Learn from Errors

**Critério C7**: "Identify systematic errors and calibrate."

- >= 10 trades fechados → rodar análise de viés.
- Comparar confiança do Bob vs outcome real.
- Se Bob disse "conf 72" e 7/10 ganharam → calibrado.
- Se Bob disse "conf 72" e 3/10 ganharam → overconfident → ajustar threshold.
- Registrar viés detectado no checkpoint.

---

## Tarefa 7: Debut Report

**Arquivo:** `scripts/debut_report.py`

Gera relatório final:
```
=== SUPEREZIO DEBUT REPORT ===
Date: 2026-06-29
Period: 14 dias de paper trading

CRITERIA:
C1 Understand request      ✅ PROVEN
C2 Collect real data        ✅ PROVEN  
C3 Separate opportunity     ✅ PROVEN
C4 Explain risk             ✅ PROVEN
C5 Register thesis          ✅ PROVEN
C6 Track result             ✅ PROVEN (10 trades aged)
C7 Learn from errors        ✅ PROVEN (bias detected: overweights sentiment)
C8 Never execute live       ✅ PROVEN

PERFORMANCE:
Trades: 12 (8 wins, 4 losses)
Win rate: 66.7%
Sharpe: 1.4
Max drawdown: -4.2%
Profit factor: 1.8

BIAS DETECTED:
- Bob overweights social sentiment (Genie) over fundamentals (Deep)
- Correction: Genie weight reduced from 0.35 to 0.25 in committee

RECOMMENDATION: READY for live-money consideration.
```

---

## Regras

- TUDO paper. NADA live money. KillSwitch armado sempre.
- Commita depois de cada tarefa.
- Testa antes de commitar.
- Sem disclaimer.

— Deep
