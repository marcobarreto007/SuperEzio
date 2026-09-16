# Módulo Coração — Roadmap de construção

**Data:** 15 de Setembro de 2026
**Estado:** roadmap aprovado para arranque; cada peça tem a sua própria spec antes de implementação
**Repositório:** SuperEzio

---

## 1. O que estamos a construir

Um arquivo permanente e vitalício de movimentos de preço para todos os ativos negociáveis
na TD Direct Investing (EUA e Canadá), com atribuição das causas prováveis desses
movimentos, e um painel que ordena ganhos e perdas em tempo de evento.

**Critério de sucesso declarado.** O objetivo não é "descobrir porque é que as coisas se
mexem e lucrar quando repetir". É **saber com honestidade se existe sinal explorável dentro
das restrições reais** — execução manual no TD, horizonte de dias, sem dados de preço
intradiários. Um sistema que responde "não há sinal aqui" com rigor demonstrável é um
sucesso; um que produz padrões bonitos sem validação é um fracasso, mesmo que pareça
melhor.

**O ML é de primeira classe — não é anexo.** Vamos ter um rio de dados (≈18 400 nomes,
eventos, eixos). Sem um gestor que **separe, cure e dê peso aos melhores caminhos**, o
painel é um dump. Esse gestor é a Peça 5: escolhe que percursos (tipo de evento × janela ×
eixo de ranking) sobrevivem, recusa o resto, e actualiza pesos quando a barreira fecha
(`river.expert`). As Peças 0–4 alimentam; o ML decide. TDD em sintéticos pode começar cedo;
treino no arquivo vivo precisa das peças a montante. Nunca tratar isto como "depois se der".

**Valor do arquivo.** O registo point-in-time de eventos mais preços do universo
norte-americano inteiro não se compra barato e não se recupera retroativamente. Continua a
valer mesmo quando o gestor de caminhos devolve peso zero — isso é uma decisão do ML, não
um pretexto para não o construir.

---

## 2. Restrições invioláveis

| # | Restrição | Consequência |
|---|---|---|
| 1 | **Custo zero absoluto.** Sem cartão, sem trial pago, sem plano que exija pagamento | Exclui Polygon, Sharadar, EODHD pago, Twelve Data splits, TMX Datalinx |
| 2 | **Execução é manual pelo Marco no TD.** O sistema não executa | O alvo é horizonte de **dias**, nunca intradiário. Barreira vertical alinhada a sessões |
| 3 | **Tudo corre localmente.** Sem nuvem | ML em CPU local; GPUs reservadas ao cérebro do MIKE |
| 4 | **Sem LLM neste módulo.** ML próprio embutido, sim; modelo de linguagem, não | Boosting + calibração, não geração de texto |
| 5 | **Nada do que já funciona pode partir** | Portão de regressão de 2 890 testes na fronteira de cada peça |
| 6 | **Integrações indisponíveis devolvem erro real** | Nunca simular sucesso, nunca inventar dados em falta |

---

## 3. Decisões já tomadas, com fundamento

| Decisão | Escolha | Porquê |
|---|---|---|
| Versão de Python | **Migrar SuperEzio inteiro para 3.12** | XGBoost ≥3.3, SHAP ≥0.52, NumPy ≥2.5, SciPy ≥1.18 já exigem 3.12+. O 3.11 é um beco que se fecha |
| Ambiente | **Criar venv próprio** (hoje corre no Python global) | Isolamento inexistente é risco por si só |
| Armazém de barras | **ArcticDB (LMDB local) + DuckDB sobre Parquet** | ArcticDB para "dá-me a série de X"; DuckDB para "todos os que caíram 3 sigmas em 2019-03-14" |
| Onde construir | **Ao lado**, não dentro do MathHub / DataHub / historical_cache | Ver secção 5. Os três estão moldados a outro problema |
| Validação cruzada | **skfolio**, nunca mlfinpy | `mlfinpy/cross_validation/combinatorial.py:156` faz `self.embargo = 0` e apaga o parâmetro. O CPCV dele nunca aplica embargo |
| Modelo principal | **LightGBM em CPU** | A 10⁵–10⁶ linhas, CPU é tipicamente mais rápido que GPU. Compilar CUDA em Windows é meio dia para ganho negativo |
| Calibração | **Venn-Abers** + MAPIE ACI | Único método com validade garantida sem assumir distribuição; ACI adapta a deriva |
| Corporate actions | **Yahoo `chart` `events=split\|div`**, `period1=0` | Única fonte grátis profunda; funciona para `.TO`, `.V`, `.CN` |
| Preços guardados | **As-traded**, com tabela de eventos ao lado | Preço ajustado alisa o degrau do dividendo — que é exatamente o que temos de detetar |
| Pista rápida (200 símbolos) | **Cortada do âmbito** | Não há preço ao minuto grátis. Sem isso seria a pista lenta com menos símbolos |

---

## 4. Universo alvo

| Segmento | Símbolos | Fonte | Cadência |
|---|---|---|---|
| EUA (Nasdaq, NYSE, Arca, AMEX, **Cboe BZX**, IEX) | **13 195** após filtrar test issues | `nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt` | Diária, após 07:30 ET |
| TSX + TSXV | **4 484** instrumentos | `tsx.com/json/company-directory/search/{tsx,tsxv}/^*` | Diária, após 09:00 UTC, crawl-delay 15 s |
| CSE | **728** | `api.twelvedata.com/stocks?exchange=CSE` (sem chave) | Semanal |
| **Total ativo** | **≈ 18 400** | | |

**Defeito conhecido no universo atual do repositório:** os 11 529 símbolos existentes
correspondem ao ficheiro oficial **menos a Cboe BZX inteira** (1 636 símbolos, onde vive
muito ETF recente).

---

## 5. Veredito de reutilização

Apurado por auditoria do repositório com `ficheiro:linha`.

### Reutilizar tal e qual

| Módulo | Porquê |
|---|---|
| `src/core/trading/triple_barrier.py` | Avaliador de barreira tripla já ligado ao `position_closer`; trata o gap na abertura corretamente |
| Padrão da caderneta JSONL (`paper_journal.py`, `recommendation_ledger.py`) | Bloqueio entre processos, quarentena de linha corrompida, id SHA256 do conteúdo, escrita atómica, guarda contra pytest escrever no ficheiro do operador |
| `src/core/math/utils.py`: `sigmoid`, `clamp`, `percentile_rank` | Já são a fonte do F51 e do crisis |
| `src/data/daily_quota.py` | Contador UTC com lock e escrita atómica |

**Correção obrigatória ao padrão da caderneta:** a implementação atual relê o ficheiro
inteiro para atualizar uma linha. Serve milhares de recomendações; **não serve milhões de
eventos**. O caminho quente do livro de eventos é *append* puro, sem `_rewrite`.

### Ressuscitar código morto em vez de escrever a quarta cópia

| Símbolo | Estado | Ação |
|---|---|---|
| `core/math/risk.py:log_return` | Só-teste; Hawkes reimplementa com `np.diff(np.log(...))` | Passa a canónico |
| `core/math/utils.py:zscore` | Exportado, zero chamadas | Passa a canónico; os 4 z-scores locais chamam-no |
| ATR em `pipeline/nodes/neural_decision.py:224-233` | Única ATR real do repositório | Passa a escrever `atr_14`, que `meta_labeling.py:179` já lê e nunca recebe |

### Não tocar — construir ao lado

| Módulo | Porquê não serve |
|---|---|
| `core/math/math_hub.py` | Relatório de 14 módulos para **um** ticker, com bootstrap de 2 000 amostras e HRP que varre SQLite. Imposto que o lote não pediu |
| `src/data/data_hub.py` (para OHLCV em massa) | Router de GET com cache de 256 entradas e pacing de 8 s. 16 700 símbolos = **~37 horas só de espera**, e não persiste |
| `core/trading/historical_cache.py` | Esquema certo (PK ticker+date, WAL) mas política de 180 dias, salta se já tiver >50 velas, e **escritores sem um único chamador** |
| `data_collector/candle_history.py` | Assembler de 794 CSV com *rescale* para treinar 1 MLP. Rescale é veneno num arquivo de preços reais |
| `core/math/portfolio.py` (HRP) | Alocação de carteira com single-linkage scipy; o universo efetivo usa complete-linkage guloso. Misturar corrompe os dois |
| `meta_labeling.evaluate_meta_labeling_gate` | Soma ponderada + sigmoid local. Não é um modelo secundário; não "calibrar" isto até parecer um booster |
| Event bus / task queue / heartbeat | Organismo do Bob: 1 pipeline por sessão, TTL 10 min, heartbeat desligado por omissão |

### Estender

| Módulo | Extensão |
|---|---|
| `src/data/data_hub.py` | Nova capability `events` para *fetches* live pontuais (Atom SEC, RSS, halts) — beneficia de cascata, breaker e pacing. **Nunca** para o lote |
| FastAPI `frontend/` + `endpoints.py` | Página nova como estáticos + `APIRouter`. Não há segundo servidor |

### Redundância a resolver

Duas correlações, dois Bollinger (um populacional, outro amostral), quatro z-scores, três
circuit breakers (um deles morto em `pipeline/resilience.py`), uma ATR órfã e um `atr_14`
fantasma que um portão lê e ninguém escreve.

### Não existe hoje no repositório

XGBoost, `IsotonicRegression`, beta de mercado em janela móvel, retorno anormal,
volatilidade EWMA, score de surpresa por quantil, feed Atom do EDGAR, feed de suspensões,
arquivo OHLCV de décadas, diário imutável de experiências.

---

## 6. As peças

### Peça 0 — Gravador cru

**Porquê existe.** Preços, halts e filings são recuperáveis (décadas de histórico
disponível). **Comunicados de imprensa não são** — o feed da PR Newswire dá 20 itens, o da
Newsfile dá 25, e o que passou desapareceu. Cada dia de atraso é um dia perdido para sempre.

**Entrega.** Um processo que sonda os feeds não recuperáveis e despeja a resposta em bruto.
Sem parsing, sem esquema, sem inteligência. Tudo o que gravar é reprocessado pela Peça 2.

**Fontes:** PR Newswire `all-news-releases-list.rss`, CNW `news-releases-list.rss`,
Business Wire (12 feeds por assunto), Newsfile `global/Last25Stories` + 4 de indústria,
GlobeNewswire, Nasdaq `feed/rssoutbound`, Reddit (via OAuth).

**Regras:** `If-None-Match` e `If-Modified-Since` sempre que o servidor der `ETag` ou
`Last-Modified`; `Accept-Encoding: gzip`; um `User-Agent` único com email de contacto real;
deduplicação por GUID com resguardo por hash de conteúdo.

**Armazenamento:** `raw/YYYY/MM/DD/<fonte>.jsonl`, append puro, padrão da caderneta sem
rewrite.

**Aceitação:** corre 24 horas sem falha de continuidade; zero GUIDs duplicados; taxa de
resposta 304 medida e reportada; a suíte continua com 2 890 verdes.

---

### Peça 1 — Universo e arquivo de preços

**1a. Registo do universo.**
Chave primária **`(mic_code, symbol, first_seen_date)`** — nunca o ticker sozinho, porque
os tickers reciclam-se (`FB` é hoje um ETF da ProShares, não o Facebook; `BBBY` foi
reatribuído). Tabela `symbol_history` com `first_seen`, `last_seen`, `delisting_date`,
`source`.

**Regra crítica:** distinguir "não apareceu no ficheiro" de "não descarreguei o ficheiro".
Um símbolo que desaparece num dia em que a descarga *falhou* não é uma deslistagem.

**1b. Arquivo de preços.** OHLCV diário **as-traded**, décadas, ~18 400 símbolos.
ArcticDB com backend LMDB para leitura por símbolo; Parquet + DuckDB para consultas
transversais.

**1c. Corporate actions.** Yahoo `query2.finance.yahoo.com/v8/finance/chart/{SYM}?events=split|div&period1=0`,
um pedido por símbolo, sufixos `.TO` `.V` `.CN` incluídos.

Regras de reconciliação:
- **O nosso preço as-traded ganha sempre.** Evento sem salto no preço = série já ajustada, não aplicar duas vezes. Salto sem evento = candidato a movimento real, vai para investigação.
- Não usar a razão `adjclose/close` do Yahoo como detetor de splits: **o `close` do Yahoo já vem ajustado a splits**; a razão dá o fator de dividendos.
- Spin-offs e stock dividends vêm codificados como split (GE `1253:1000`, CNQ `1021:1000`). Ajustar continuidade, mas rotular diferente.
- Símbolo deslistado (404 no Yahoo): **congelar a série e nunca fundir com o homónimo reciclado.**

**1d. Lote noturno.** Por símbolo e por dia: retorno em log, beta contra modelo de mercado
em janela móvel, retorno anormal, volatilidade EWMA, volume relativo, gap de abertura
versus movimento intradiário, score de surpresa por quantil empírico.

Base estatística: `statsmodels.OLS` com **`cov_type="HAC"` (Newey-West) obrigatório** —
retornos têm heterocedasticidade e autocorrelação, e os erros-padrão por omissão mentem.
`arch` para volatilidade condicional GARCH.

Calendário: `exchange_calendars` + `pandas_market_calendars`. **Usar `early_closes()`, não
só `valid_days()`** — a véspera de Natal fecha às 13:00 e gera falsos positivos
sistemáticos de volume.

**Aceitação:** 18 400 símbolos ingeridos; splits reconciliados; **o top de maiores quedas
não contém um único split**; suíte com 2 890 verdes.

---

### Peça 2 — Livro de eventos

**Entrega.** Registo append-only normalizado, com carimbo de hora **e precisão do carimbo**.

**O relógio do sistema.** O CSV de halts da NYSE
(`nyse.com/api/trade-halts/historical/download`) traz todos os halts de **todas** as bolsas
americanas, com símbolo em coluna e hora ao segundo, **incluindo pausas LULD** — a bolsa a
declarar oficialmente que o preço saiu da banda. É o detetor de "aconteceu alguma coisa",
para o universo todo, num pedido. Endpoint `/current/download` com `Cache-Control: max-age=300`
para o vivo; `/historical/download` com intervalo do dia às 20:15 ET para reconciliação.

**Eventos já classificados na origem.** Business Wire publica um feed por assunto — fusões,
falências, processos, desdobramentos, dividendos. O ticker vem no início da descrição no
formato `(NYSE:CTRE)`. Dispensa classificação de texto livre.

**SEC.** `browse-edgar?action=getcurrent&type=<FORM>&output=atom` dá canais Atom separados
por formulário: `4` (insiders), `SC 13D`/`SC 13G` (acumulações >5%), `8-K`, `424B5`, `25`
(deslistagem), `8-A`. Sete pedidos por minuto = 0,12 req/s contra limite de 10.
**`User-Agent` com contacto é obrigatório** — UA de browser dá 403.

**Outras:** FINRA `api.finra.org/data/group/otcMarket/...` (sem chave), Nasdaq
`rssoutbound` com campo `<nasdaq:tickers>` estruturado, calendários Nasdaq
(earnings/dividends/splits), Reg SHO, `TradingSystemAddsDeletes.txt`, `frames` do XBRL.

**Camada de browser.** Fontes renderizadas em JavaScript ou bloqueadas a clientes HTTP:
boletins da CSE, halts da CIRO, boletins do TSXV, Bluesky. **Prioridade: intercetar os
pedidos de rede e descobrir a API JSON por baixo** — se existir, chama-se direto sem
browser, que é ordens de grandeza mais barato. Browser em cadência de 15–30 minutos, nunca
de minuto a minuto.

**Backfill:** EDGAR full-index (1993→hoje, fiável para Form 25 a partir de Abril/Maio de
2006), NYSE historical halts, reprocessamento do que a Peça 0 gravou.

**Orçamento medido:** ~18 000 pedidos/dia sobre 20+ domínios. Nenhum perto do seu limite
publicado.

**Aceitação:** um evento conhecido (um 8-K real) aparece no livro com carimbo correto em
menos de 2 minutos; reconciliação de fim de dia não encontra buracos; 2 890 verdes.

---

### Peça 3 — Atribuição de causa

**Entrega.** Junção temporal entre movimentos anormais (Peça 1) e eventos (Peça 2), com
grau de confiança e evidência preservada.

**Janela assimétrica:** um 8-K arquivado às 16:10 explica o movimento de **amanhã**; um
arquivado às 09:00 explica o de hoje. Regra de precedência quando há vários candidatos.

**Correção estatística obrigatória.** Se 300 empresas de biotecnologia reagirem ao mesmo
anúncio da FDA no mesmo dia, **isso não são 300 observações independentes — é
aproximadamente uma**. Sem correção de correlação transversal, saem valores-p espetaculares
e falsos. Implementar segundo a especificação do `robust-eventstudy` (teste de
Ibragimov-Müller para poucos clusters, t ajustado de Kolari-Pynnönen, intervalos BCa) com
`statsmodels` e `scipy`.

**Interface:** apresenta a evidência; correção humana opcional num clique, registada como
tal.

**Aceitação:** num conjunto de eventos conhecidos, a atribuição acerta o evento correto
acima de um limiar declarado *antes* de medir.

---

### Peça 4 — Painel de ranking

**Entrega.** Página nova no mesmo FastAPI, com ranking vivo e histórico por papel.

**Perspective** (FINOS, Apache-2.0) renderiza milhões de linhas no browser via WebAssembly,
com pivôs e filtros do lado do cliente — resolve as ~100 000 linhas de movimentos anormais
por ano sem paginação à mão. **lightweight-charts** (TradingView, 45 KB) para o gráfico com
marcadores de evento sobrepostos.

**Eixos do ranking, combinados com pesos adaptativos:** retorno anormal (ajustado a mercado
e setor), retorno bruto, score cumulativo vitalício, fator de surpresa (movimento relativo
à volatilidade típica).

**Aceitação:** carrega 100 000 linhas em tempo aceitável medido; testes de browser no padrão
já existente no repositório.

---

### Peça 5 — Gestor de caminhos (ML de primeira classe)

**Papel.** Não é um modelo "por cima" do painel. É quem **cura o rio e pesa os caminhos**.
Com muitos dados, a pergunta operacional é: o que entra, o que sai, e com que peso cada
percurso compete no ranking. LightGBM/CatBoost, `river.expert`, selecção dentro da dobra e
DSR honesto são o mecanismo — não um extra.

**Rótulos.** `triple_barrier.py` reutilizado. Barreiras assimétricas, largura escalada pela
volatilidade condicional do GARCH, **barreira vertical alinhada ao calendário de sessões**
(não a dias corridos) — coerente com a restrição de execução manual.

**Modelos.** LightGBM principal em CPU; CatBoost como segundo independente. Meta-rotulagem:
o secundário prevê P(sucesso | lado), não a direção.

**Calibração.** Venn-Abers para probabilidade com validade garantida; MAPIE
`TimeSeriesRegressor` com `method="aci"` para adaptar a deriva — `.update()` e
`.adapt_conformal_inference()` quando a recompensa chega.

**Validação.** `skfolio.model_selection.CombinatorialPurgedCV` com purga e embargo
verificados. `.summary()` para confirmar quantas observações foram purgadas.

**Armadilha número um do projeto.** A seleção de variáveis do `tsfresh` (700+
características) **tem de correr dentro de cada dobra**, nunca antes. Selecionar com todos
os dados e validar depois torna o Deflated Sharpe ficção.

**Registo.** MLflow local (`sqlite:///runtime/mlruns.db`, sem conta, sem nuvem) + Optuna com
storage RDB. **Sem contar todas as tentativas, incluindo as que falharam, o Deflated Sharpe
não tem denominador.**

**Adaptação.** `river.drift` (ADWIN, Page-Hinkley, KSWIN) decide *quando* re-treinar, em vez
de um calendário fixo. `river.expert` para os pesos adaptativos com recompensa atrasada — o
peso atualiza-se quando a barreira fecha, não quando a previsão foi feita.

**Referência de arquitetura:** ler `freqtrade/freqai/` antes de desenhar o re-treino
contínuo — resolve este problema há anos, em produção.

**Interpretabilidade sem treino.** `stumpy` (matrix profile) responde a "este padrão de 20
dias já aconteceu antes, em qualquer símbolo, em qualquer altura?" — e o que aconteceu
*depois* desses análogos é uma distribuição empírica, não uma previsão. Correr sob procura,
sobre subconjunto, nunca sobre tudo todas as noites.

**Importância agrupada.** SHAP por variável engana com variáveis correlacionadas. MDA por
clusters (agrupar por correlação, permutar o grupo inteiro) — ~60 linhas, não há
implementação viva fiável.

**Aceitação:** o Deflated Sharpe é reportado com o número real de tentativas; a cobertura
conforme é medida e bate o nominal.

---

## 7. Regras transversais

### Portão de regressão

**Linha de base de 15 de Setembro de 2026: 2 890 verdes, 0 vermelhos, 3 saltados.**
A suíte completa demora 13 minutos e 30 segundos.

Disciplina: testes dirigidos durante o trabalho; **suíte completa na fronteira de cada
peça**, antes de a dar por fechada. Qualquer vermelho a partir de agora é nosso.

Nota operacional: os 13 testes de browser exigem os binários do Playwright
(`python -m playwright install chromium`). Estão guardados numa pasta temporária do sandbox
que pode ser limpa; se voltarem a falhar com "executable doesn't exist", é isto.

### Manifesto com limitações legíveis por máquina

Todo o conjunto de dados congelado carrega um manifesto com: hash SHA256 de cada fonte, do
manifesto de aquisição e do output; política de ajuste declarada; e uma lista `limitations`
por extenso.

Consequência que tem de ficar escrita: séries com ajuste retroativo **não são reproduzíveis
a partir do fornecedor**. O hash prova o que foi usado, não permite obter o mesmo outra vez.
O ficheiro congelado é **o artefacto** e precisa de cópia de segurança como se fosse código.

### Registos gratuitos a fazer antes de começar

| Serviço | O que dá | Custo |
|---|---|---|
| Alpha Vantage | `LISTING_STATUS&state=delisted` (25 pedidos/dia) | Email, sem cartão |
| Reddit (app OAuth) | **100 pedidos/minuto** em vez de 1 | Registo + aprovação Responsible Builder |

### Limites operacionais a respeitar

- SEC: 8 req/s (margem sobre o limite de 10), `User-Agent` com contacto obrigatório
- Nasdaq trade halts RSS: 1 pedido por minuto (regra escrita)
- `tsx.com`: `Crawl-delay: 15`
- GlobeNewswire: estrangula por IP de forma agressiva — 1 pedido/minuto, nunca bursts
- **`apps.tmx.com` e `/resource/` do `tsx.com`: `Disallow` no robots — não automatizar**

---

## 8. Riscos assumidos

Aceites de olhos abertos após discussão explícita.

| Risco | Natureza | Mitigação possível |
|---|---|---|
| **Execução manual** — o retorno anormal em nomes líquidos é arbitrado em minutos; quando vemos, acabou | Limite físico do arranjo | Horizonte de dias desde o desenho; alvo em efeitos lentos e documentados |
| **Sinal fraco** — com ~100 000 eventos/ano e centenas de variáveis, a probabilidade de encontrar padrões inexistentes é esmagadora | Estatístico | Validação purgada, DSR com denominador honesto, correção de teste múltiplo |
| **Deslistados invisíveis** — Yahoo devolve 404; sem preço histórico de mortos há viés de sobrevivência | Dado indisponível a custo zero | Arquivar snapshots diários **desde já**; congelar séries mortas |
| **Corporate actions incompletas** — sem fonte canadiana estruturada; TSXV deslistado é cego | Dado indisponível a custo zero | Yahoo como espinha dorsal; reconciliação contra preço as-traded; marcar o que não fecha |
| **Tamanho** — seis peças, meses de trabalho | Gestão | Decomposição com aceitação por peça; cada uma tem valor sozinha |

---

## 9. Ordem e dependências

```
Preparação: migrar para Python 3.12 em venv próprio  →  validar contra 2 890 testes
     │
     ├─ Peça 0 (gravador cru) ──────────────┐   [independente, arranca já]
     │                                       │
     ├─ Peça 1 (universo + preços) ─────┬────┤
     │                                  │    │
     └─ Peça 2 (livro de eventos) ──────┤    │  [reprocessa o que a 0 gravou]
                                        │    │
                       Peça 3 (atribuição) ◄─┘  [precisa da 1 e da 2]
                                        │
                       Peça 4 (painel) ◄─┤     [precisa da 1; melhor com a 3]
                                        │     [mostra; não aprende pesos]
                                        │
                       Peça 5 (ML gestor) ◄──┘ [primeira classe: cura + peso]
                                               [TDD sintético cedo; treino vivo depois de 1–3]
```

Cada peça: spec própria → plano próprio → implementação → suíte completa verde → fecho.
Não se avança sem a anterior fechada.

---

## 10. Fora do âmbito

- **Pista rápida de 200 símbolos ao minuto.** Não há preço intradiário grátis. Volta como
  Peça 6 se aparecer fonte.
- **Execução de ordens.** O Marco executa; o sistema investiga.
- **LLM neste módulo.**
- **Distribuição a terceiros.** Várias fontes são grátis mas não licenciadas para
  redistribuição (Nasdaq permite "one *unaltered* copy"; TMX proíbe obras derivadas). Uso
  pessoal numa máquina local; no dia em que deixar de ser pessoal, a análise muda por
  completo.
