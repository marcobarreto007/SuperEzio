# O que o comitê de investimento tem que o SuperEzio não tem

13/10/2026. Mapeamento do SuperEzio (4 capacidades) cruzado com o comitê
(`C:\Users\marco\comite-investimento`) e com o pente-fino dele.

**Veredito curto: copiar do comitê para o Ezio é pouca coisa — o Ezio já tem
melhor em quase tudo. O que falta no Ezio não é código, é combustível e hábito.
E é aí que o comitê ensina algo.**

---

## O que o Ezio JÁ TEM (e é melhor — não copiar nada de fora)

| Capacidade | Onde | Estado |
|---|---|---|
| Brier multiclasse + encolhimento + pesos que entram na decisão | `src/core/trading/outcome_learning.py:320-414`, `expert_stats` :352 | Código sério, **zero observações** |
| Evidência com hash canónico e congelamento | `src/core/evidence/pack.py:60`, `snapshot.py:98` | Ligado por omissão |
| Bind de números (recusa afirmação sem lastro) | `snapshot.py:430-475` | Ligado por omissão |
| Grounding de ticker (censura dura) | `grounding.py:24`, `nodes/agent.py:800-894` | Ativo |
| Triple barrier + meta-labeling + fechador idempotente | `triple_barrier.py`, `position_closer.py` | Testado ponta a ponta, dry-run por omissão |
| Cadeia de gates de risco (risco total 1,5%, assimetria 2,5:1, taxa zero, MARKET proibida, kill switch derivado, money gate CA) | `tool_executor.py:432-710` | Mais completa que o padrão OSS |
| Caderneta append-only com "real ganha do contrafactual" | `recommendation_ledger.py:42-65` | Viva, 1 linha real |

A matemática do placar do comitê (Brier, skill, encolhimento `n/(n+20)`) **parece**
a mesma que já está em `outcome_learning.py` — mesma forma, mesmo K=20, mesmo teto
2,0. **Mas o comportamento não é, e o do comitê é o são.**

CORREÇÃO (14/10/2026, investigação de calibração): o Brier do Ezio é multiclasse
*vs.* uma referência fixa de 2/3, e isso torna a métrica imprópria — um expert que
**erra** com confiança 0,70 ainda bate o baseline uniforme (0,535 < 0,667), e o
ponto de equilíbrio é c≈0,80. Ou seja: **o Ezio premia confiança, não acerto**, e um
moeda-ao-ar confiante tira peso máximo. No Brier binário do comitê isso não acontece:
mover massa para longe de 0,50 obriga a pôr massa no lado errado (c=0,70 com 50% de
acerto dá skill −0,16). O que há a portar do Ezio é outra coisa — o deadband de
custo, a referência por taxa-base e o ledger com hash. Ver a lista de itens portáveis
no fim deste documento.

---

## O que o comitê tem e o Ezio NÃO tem

### 1. O prior cego do Marco (medir se o humano agrega)
No comitê, a tua probabilidade é registada **antes** de veres a análise
(`diario.py pre`), e o placar compara-a com o comitê. Em um ano sabes se o
comitê vale mais que o teu julgamento — ou não.
No Ezio: não existe (busca por `operator_prior`/`human_baseline` → zero).
É o único sítio do teu ecossistema que mediria **tu**.

### 2. Advogado do diabo obrigatório + réplica medida
Grep por `advogado|pre-mortem|dissiden` em `src/` → **zero**.
O comitê ataca a posição dominante, faz pré-mortem, e cada analista responde —
e o placar mostra se quem mudou de ideia melhorou ou piorou a calibração.
No Ezio os experts convergem e nada os obriga a atacar o consenso.

### 3. Previsões curtas e datadas (30-180 dias) por membro
O placar do comitê enche-se em meses porque cada analista abre 1-3 previsões
verificáveis de curto prazo.
No Ezio a resolução é por barreira (stop/alvo/prazo) ou pela caderneta — mais
lento, e a skill `tese-tracker` é manual: **1 tese (`SPY.json`, 05/09) e zero
resoluções**, com `C6 ThesisRecord` ainda aberto no TASK_BOARD.

### 4. Placar visível
O comitê tem `/placar` com Brier, viés de otimismo e "a réplica ajudou?".
No Ezio o motor existe e **nada o mostra**: o cockpit devolve
`weights: "unweighted"` (`heart_endpoints.py:158`). O teu `CLAUDE.md` diz
"P5 aprende pesos; o painel mostra" — a segunda metade é verdade, a primeira não.

---

## O que copiar do PENTE-FINO (como checklist de armadilhas)

As mesmas quatro classes de defeito podem existir no Ezio. Vale verificar:

1. **Falha de rede que vira zero em silêncio.** No comitê, `info()` falho zerava
   os limites da política. No Ezio, o equivalente seria um feed do Coração ou do
   IBKR falhar e o número virar 0 em vez de erro. O Ezio já é fail-closed em
   vários sítios (`td_universe`, `money_gate`) — vale varrer os que não são.
2. **Cachear ausência.** `fillna(0)` e cache de resultado vazio foram dois bugs
   no comitê. Verificar se algum cache do Ezio guarda "vazio" como se fosse dado.
3. **Quórum.** No comitê, um memo só produzia "consenso forte". No Ezio,
   `calculate_weighted_expert_consensus` com poucos experts respondeu o mesmo?
4. **Denominador que encolhe.** No comitê, previsão "indeterminada" saía da conta
   sem aparecer. No Ezio, `SKIP_HORIZON_PENDING`/`SKIP_NO_MARKET_DATA` são
   tipados (bom) — mas o que sai da conta tem de aparecer em algum lado.

---

## Os 3 passos que eu faria, por ordem

1. **`memory: project` nos 29 agentes.** É a tua regra global e está a zero aqui.
   Ganho imediato, risco nulo, nada a decidir. (No comitê eram 0/7, já corrigido.)
2. **Dar combustível ao que já existe:** reportar a execução no TD (o
   `record_executed_outcome`) e ligar o fechador fora do dry-run. O motor de
   aprendizado está construído e desligado por falta de desfecho — não por falta
   de código.
3. **Roubar duas ideias de desenho ao comitê:** o **prior cego** (registas a tua
   probabilidade antes de ver o Bob) e o **placar visível** (endpoint que mostra
   Brier e skill por expert). São as duas peças que transformam o motor existente
   em algo que te diz alguma coisa.

**A lição do comitê não é o código — é o ciclo.** Ele é leve, tem um comando que
força o ritual (prior → análise → decisão → revisão mensal) e por isso tem
hipótese de ser usado. O Ezio tem o motor mais sério dos dois e nenhum hábito
que o alimente.
