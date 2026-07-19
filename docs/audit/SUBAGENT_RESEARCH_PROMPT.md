# Prompt para subagentes — Continuação da auditoria SuperEzio

> Cole este prompt inteiro em qualquer subagente/modelo mais barato que você lançar.
> Ele é autocontido: não assume que o subagente tem contexto desta conversa.

---

## Contexto (leia antes de tudo)

Você está auditando o repositório `SuperEzio` em `C:\Users\marco\Desktop\SuperEzio`. É um
sistema de análise financeira multi-agente (não é day-trade automático — tem gates
`SUPEREZIO_LIVE_TRADING_DISABLED` e `SUPEREZIO_RESEARCH_PAPER_ONLY` ativos por padrão).

Regra crítica do projeto, leia `CLAUDE.md` e `.f51/GITHUB_POLICY.json` antes de qualquer coisa:
**GITHUB É PROIBIDO NESTE PROJETO.** Nunca rode `git push`, `git pull`, `git fetch`, `gh`, nem
abra PR. Modo é `DISK ONLY`. Commits locais são permitidos e esperados após cada mudança.

Já existe uma auditoria componente-por-componente feita e commitada em `docs/audit/`:
- `phase1_config_math.md` — config e matemática
- `phase2_model_gateway.md` — model gateway / fallback entre provedores
- `phase3_datahub.md` — roteamento de dados de mercado
- `phase4_expert_isolation.md` + `phase4b_expert_isolation_fix.md` — isolamento de dados
  entre especialistas (já corrigido parcialmente)

**Leia esses 5 arquivos primeiro.** Eles têm achados confirmados com linha exata de código.
Não repita esse trabalho. Sua missão é continuar de onde parou.

## O que ainda falta ser auditado (não foi tocado nas fases 1-4)

Cada um destes é um componente separado. Trate cada um como investigação independente —
não assuma que um está bom porque outro está. Para cada achado, cite arquivo:linha exatos,
nunca "acho que" ou "provavelmente".

1. **F51 Verdict Engine** (`src/f51/*.py` — graph, formulas, scoring, detectors, gates)
   - O `f51_module` em `math_hub.py` já foi parcialmente auditado (achou `consensus=0.65`
     hardcoded, já corrigido). Mas o motor `f51/formulas.py` em si — `unified_decision`,
     `heuristic_uncertainty`, `DecisionFactors` — nunca foi lido linha a linha.
   - Pergunta a responder: quais outros valores dentro de `f51/*.py` são heurísticos/fixos
     vs. calculados de dado real? Documentar cada um.
   - Também auditar `backend/data_platform/provenance/source_catalog.json` se existir aqui
     (pode não existir — este é outro projeto, `veribay`, não confundir os dois).

2. **SDCA Firewall** (`src/core/risk_firewall/*.py`)
   - Alegado no `CLAUDE.md`: "não chama LLM, rede ou broker, não faz previsão de preço" —
     regras determinísticas para FOMO, revenge trading, alavancagem, spread, liquidez,
     slippage, sinal atrasado, qualidade de dado.
   - Verificar se isso é literalmente verdade lendo o código: existe alguma chamada de rede
     ou LLM escondida? As regras são hardcoded ou configuráveis? Que fração das operações
     ele bloquearia dado um histórico de exemplo?

3. **Neural Decision Expert** (`src/experts/neural_decision/*.py`, `src/experts/technical_neural/*.py`)
   - Dois módulos com nomes parecidos (`neural_decision` vs `technical_neural`) — o
     `.f51/RISK_REGISTER.md` (INV-R do tipo "duplicate split?") já levanta a dúvida de se são
     legado duplicado ou intencionalmente distintos. Resolver com leitura de código: eles têm
     lógica diferente ou um é dead code do outro?
   - Verificar se o MLP (PyTorch) é treinado com dado real ou se retorna valores fixos/mock
     (mesmo padrão que achamos em `_quantum_module` — seed fixa, constante hardcoded).

4. **RAG / ForensicRAG** (`src/core/rag/*.py`)
   - `forensic_rag.py`, `fraud_rag.py`, `macro_dataset` (ou nomes equivalentes — confirmar
     nomes reais com `ls src/core/rag/`).
   - Perguntas: o índice vetorial (Chroma/FAISS/outro) está sendo populado com dado real ou
     está vazio/mock? Se a busca não encontrar nada, o que acontece — erro claro ou resposta
     fabricada? Isso é o mesmo padrão de risco do achado da Fase 3 (`{}` tratado como sucesso).

5. **PennyLab** (`src/experts/pennylab/*.py`, 14 arquivos)
   - 4 experts de penny stock + scoring + hooks de RAG + lab journal + CLI + schemas.
   - Este módulo nunca foi auditado. Mapear: quais dados reais ele usa vs. simulados? O
     backtest dele (`penny_momentum.py`, já mencionado na Fase 1 do math_hub) é diário/swing
     ou intradiário de verdade? Ele reusa `EXPERT_CONTEXT_MODULES` da Fase 4b ou tem seu
     próprio pipeline de contexto sem isolamento?

6. **Camada de execução / broker** (`src/core/trading/*.py`, `src/adapters/*.py`)
   - `broker_reconciler.py`, `paper_journal.py`, `kill_switch` (achar o arquivo certo),
     `position_sizer`, `order_builder`, `approval_gate`, adaptador IBKR.
   - Já sabemos que `trading_engine_live.py` tem os gates `SUPEREZIO_LIVE_TRADING_DISABLED`
     e `SUPEREZIO_RESEARCH_PAPER_ONLY` (Fase 2 anterior tocou nisso de raspão). Auditar se
     TODOS os caminhos de execução real respeitam esses gates, ou se existe algum atalho
     (ex: uma função que ainda chama a IBKR direto sem checar a env var).
   - Isso é o componente de MAIOR risco financeiro real — trate com o máximo de rigor.
     Qualquer caminho que envie ordem real sem checar os gates é achado CRÍTICO.

7. **Idempotência e dead-letter queue** (`src/core/idempotency/*.py` se existir)
   - Existe uma skill do projeto chamada `f51-idempotency` mencionando "idempotency key
     persistente, deduplicação cross-process, dead letter queue para ordens que falham
     journal" — verificar se isso está implementado ou é só a skill/aspiração.

8. **Segurança** (`src/core/security/*.py`, superfície de `search_web`/`extract_web` no
   DataHub já anotada na Fase 3 como "fora de escopo, revisar depois")
   - Rodar um scan de padrões perigosos: `eval(`, `exec(`, `subprocess` com `shell=True`,
     f-strings interpoladas direto em query SQL, segredos hardcoded fora de `.env`.
   - Achado pendente da Fase 3: `data_hub.py` `search_web`/`extract_web` passam `query`/`url`
     do usuário para `subprocess.run(["node", path, query])` — confirmar se `shell=True`
     nunca é usado em lugar nenhum do projeto (grep completo) e se `query`/`url` podem conter
     caracteres que quebrem isso mesmo sem shell=True.

9. **Reprodutibilidade e cache do comitê de pesquisa** (`src/core/pipeline/nodes/experts.py`)
   - A Fase 4b implementou `EXPERT_CONTEXT_MODULES` e `build_judge_context`, mas o cache
     `_EXPERT_CACHE` (dict em memória, `_cache_key` usa hash de role+ticker+provider+context)
     ainda não foi testado com uma chamada real ao DeepSeek. Se você tiver credenciais de
     teste (não crie nem peça credenciais reais — só use se já estiverem configuradas no
     ambiente), rode `node_expert` fim-a-fim para os 6 roles + 1 judge e confirme:
     - JSON de saída é válido e bate o schema esperado por role?
     - O contexto fatiado por role (`EXPERT_CONTEXT_MODULES`) é suficiente para o modelo
       responder sem alucinar (ex: momentum não inventa fundamento que não recebeu)?
     - `provider_used`/`fallback_occurred` aparecem corretos no resultado?

## Regras de conduta (não negociáveis)

- **Não rode `git push/pull/fetch/gh`.** Nunca. Se achar que precisa, pare e reporte bloqueio.
- **Não corrija nada sem evidência de linha exata.** "Parece que" não é achado, é suspeita —
  marque como suspeita, não como confirmado.
- **Não invente dado, credencial, ou resultado de teste.** Se não puder rodar algo (sem
  servidor, sem GPU, sem credencial), diga explicitamente "não testado, motivo: X".
- **Separe SUGESTÃO de CORREÇÃO.** Se encontrar um bug real e pequeno (escopo reversível,
  como os fixes já feitos em `math_hub.py`/`gateway.py`/`experts.py`), pode corrigir — mas
  documente antes/depois e rode os testes relevantes (`python -m pytest tests/ -k <módulo> -q`)
  comparando com o estado anterior via `git stash` se tiver dúvida sobre regressão pré-existente.
- **Nunca misture correção de bug com feature nova** na mesma mudança (regra do próprio
  `CLAUDE.md` do projeto).
- **Todo commit local deve ter mensagem explicando o quê e por quê**, no mesmo estilo dos
  commits já existentes (`fix(escopo): resumo` / `docs(escopo): resumo` / `save(session): resumo`).
- Ao final, escreva um relatório novo em `docs/audit/phaseN_<nome>.md` seguindo exatamente o
  formato dos 5 relatórios já existentes (achado, arquivo:linha, severidade, verdict
  CONFIRMED/PLAUSIBLE, resumo executivo em tabela no final).
- Atualize `.f51/checkpoints/latest.json` e `.f51/TASK_BOARD.md` ao terminar, seguindo o
  padrão do commit `db32f53` (`save(session): ...`) já no histórico.

## Formato de entrega esperado

Para cada componente investigado (1-9 acima), produza:

```markdown
# Fase N — <nome do componente>

Gerado: <data>
Escopo: <arquivos exatos>
Método: leitura direta de código [+ execução de teste, se aplicável]

## Achados

### <N.1> — <título curto>
- Arquivo: `path:linha`
- <descrição do achado com trecho de código citado>
- Verdict: CONFIRMED | PLAUSIBLE (não verificado por execução)
- Classe: ALPHA | FILTRO | RISCO | EVIDÊNCIA | SÍNTESE | INFRAESTRUTURA
- Severidade: BAIXA | MÉDIA | ALTA | CRÍTICA

## Resumo executivo

| Achado | Classe | Severidade | Status |
|---|---|---|---|
| ... | ... | ... | ... |

## Próximo passo
```

Não pare para perguntar ao operador durante a investigação — só pare se estiver genuinamente
bloqueado (ex: precisa de uma credencial que não existe, precisa rodar `git fetch` para algo).
Nesses casos, documente o bloqueio no relatório e siga para o próximo item da lista.
