# Agent Lab — Evolve the Agent Army

Goal: Improve agent quality through systematic testing and replacement.

## Procedure

### Step 1: Evaluate Current Agents
Deploy **agent-explorer** to review all agent reports.
Output: strong agents, weak agents, duplicates, gaps.

### Step 2: Benchmark Weak Agents
Deploy **agent-benchmarker** to test weak agents against candidates.
Output: score table, winner, loser, why.

### Step 3: Replace Failing Agents
Deploy **agent-replacer** for each agent that scored < 16.
Output: deprecated agent, new candidate, test task, promotion criteria.

### Step 4: Validate Replacements
Run the same task with old and new agent in parallel.
Compare evidence ratio, bugs found, scope compliance.

### Step 5: Promote or Rollback
- Winner (score > 20, 0 scope violations) → promote to active
- Loser → keep in deprecated/
- Tie → keep both, re-benchmark with harder task

## Agent Lifecycle States
```
candidate → (benchmark win) → active → (3 elite scores) → elite
                                                  ↓ (3 failures)
                                            deprecated → (30 days) → killed
```

## Scoring (per agent, per task)
| Critério | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| Evidência | 0 claims | 1-2 c/ src | 3-5 c/ src | maioria | quase todas | todas |
| Utilidade | irrelevante | marginal | alguma ação | reduziu incerteza | ação clara | múltiplas ações |
| Precisão | tudo errado | maioria errada | misto | maioria certa | quase tudo certo | perfeito |
| Escopo | violou tudo | violou proibidos | vago | ok | bom | preciso |
| Verificação | sem gate | gate vago | gate ok | gate testável | gate rodado | gate passou |
| Concisão | ilegível | >1000 palavras | 500-1000 | <500 ok | denso | cirúrgico |

Target: 26-30 for elite, 0-9 for immediate replacement.
