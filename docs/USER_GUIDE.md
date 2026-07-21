# SuperEzio -- Guia do Usuario (Trader)

Bem-vindo ao SuperEzio. Este guia foi feito para quem quer usar a ferramenta sem precisar entender de programacao. Se voce negocia acoes, acompanha o mercado ou quer testar estrategias, aqui voce encontra o basico para comecar.

---

## 1. Comece em 5 minutos

### O que voce precisa

- Um computador com Windows, macOS ou Linux
- Python 3.11 ou superior instalado
- Acesso a internet (para baixar dados do mercado)

### Passo a passo rapido

**Windows:**

1. Abra o terminal (PowerShell) na pasta do SuperEzio
2. Digite:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

3. Depois de instalar, inicie o servidor:

```powershell
python -m agent_server.main
```

4. Abra o navegador em: **http://localhost:8002**

**Linux / macOS:**

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m agent_server.main
```

No navegador, voce ve a tela principal do SuperEzio. Pronto.

### Quer um atalho?

Na pasta do projeto, execute `launcher.ps1` (Windows) ou `./setup_superezio.sh run` (Linux/macOS). O sistema inicia e abre o navegador automaticamente.

---

## 2. O que e cada coisa

O SuperEzio e uma "bancada de trabalho" para analisar acoes. Nao e uma corretora. Nao executa ordens automaticas (a nao ser que voce configure explicitamente -- e isso esta DESLIGADO por padrao).

A tela principal tem tres areas:

```
+--------------------------------------------------+
|  BARRA SUPERIOR: busca de acoes, timeframe, status  |
+----------------------------------+---------------+
|                                  |  PAINEL DE    |
|  GRAFICO DE VELAS               |  ESPECIALISTAS|
|  + precos ao vivo               |               |
|                                  |  F51, SDCA,   |
|                                  |  Neural,      |
|  ORDENS E POSICOES              |  Trinity...   |
|  (paper trading / simulacao)    |               |
+----------------------------------+---------------+
|  BOB: chat com seu analista AI   | BARRA DE STATUS  |
+----------------------------------+---------------+
```

### Bob: seu analista financeiro AI

Bob e o assistente de chat. Clique no icone de mensagem no canto inferior direito para abrir o chat com ele.

Bob enxerga o grafico que esta na sua tela. Se voce digitar "Analisa PETR4", ele puxa os dados da acao, consulta os especialistas do sistema e responde com uma analise. Ele nao "chuta" -- ele usa dados reais de mercado e uma equipe de especialistas internos para formar a resposta.

Voce pode perguntar:
- "O que acha de AAPL?"
- "Tem alguma oportunidade hoje?"
- "Qual o risco de comprar TSLA agora?"
- "Mostra os scores dos especialistas para MGLU3"

**Importante:** Bob e uma ferramenta de analise, nao um oraculo. Sempre use seu proprio julgamento.

### Grafico de velas com indicadores

O grafico ocupa 70% da tela. Ele mostra:
- **Velas (candlesticks)** -- verdes quando o preco sobe, vermelhas quando cai. Cada vela mostra abertura, fechamento, maxima e minima do periodo.
- **Precos ao vivo** -- ultimo preco, variacao, alta, baixa e volume na barra superior.
- **Timeframes** -- voce escolhe: 1 dia, 1 semana, 1 mes, 3 meses, 6 meses, 1 ano, 5 anos. O padrao e 6 meses.
- **Crosshair** -- passe o mouse sobre o grafico para ver valores exatos de cada vela.

Para mudar de ativo, digite o ticker (ex: "AAPL", "PETR4", "TSLA") no campo de busca na barra superior e pressione Enter.

### Expert Panel: equipe de analistas

Do lado direito da tela fica o painel de especialistas. Cada e um analista diferente com uma funcao especifica. Todos trabalham em paralelo quando voce faz uma pergunta ao Bob.

| Card | Nome | O que faz |
|------|------|-----------|
| **F51** | Veracity Consensus | Mede a "veracidade" dos dados e o consenso geral. Mostra um grafico circular com a pontuacao geral e barras para cada fator: veracidade, consenso, robustez, incerteza, perigo. |
| **SDCA** | Risk Firewall | Avalia o risco da operacao. Analisa: latencia, spread, hype social, qualidade dos dados, sinais de FOMO, alavancagem, slippage. Pode BLOQUEAR uma operacao se o risco for alto. E o "guarda de seguranca" do sistema. |
| **NRL** | Neural Prediction | Usa um modelo de IA para prever direcao de preco. Mostra probabilidades para alta, baixa e estabilidade. Inclui botoes de "confianca alta", "risco de cauda", etc. |
| **TRI** | Trinity Deliberation | Reune as opinioes de todos os especialistas e tenta chegar a um consenso. O veredito final pode ser SUPPORT (apoio a operacao), BLOCK (bloqueio) ou NEUTRAL (neutro). |
| **GRD** | Guardrail Hub | Barreiras de seguranca em 8 camadas, desde seguranca de entrada ate deteccao de fraude e crise. Mostra quantas camadas estao OK. |
| **MNG** | Mangala Tracker | Acompanha as operacoes simuladas de penny stocks que o Mangala esta "cacando". Mostra o patrimonio em compounding (crescimento progressivo). |

Cada card tem uma barra de confianca (trust bar) que mostra o nivel de confiabilidade daquele especialista no momento.

### Mangala: cacador de oportunidades baratas

Mangala e o "cacador de penny stocks" do SuperEzio. Ele varre o mercado procurando acoes abaixo de US$ 10 com alto volume e sinais de momentum.

Cada acao analisada recebe uma nota de 0 a 100:

| Score | Sinal | O que significa |
|-------|-------|-----------------|
| 80+ | "MANGALA!" | Oportunidade de alta conviccao. O sistema identifica anomalia de volume, acumulacao de grandes investidores (whales) e catalisadores positivos. |
| 60-79 | "WATCH" | Setup potencial. Merece atencao, mas ainda nao esta maduro. |
| 40-59 | "MEH" | Nao esta pronto. Ignorar por enquanto. |
| < 40 | "PASS" | Nao vale o risco. |

Os fatores que compoem a nota:
- **Volume anormal** (0-30 pts): volume muito maior que a media dos ultimos 20 dias
- **Whales** (0-25 pts): deteccao de grandes compradores ("baleias")
- **Momentum** (0-20 pts): forca da tendencia nos ultimos 5 dias
- **RSI** (0-15 pts): indicador de momento entre 40 e 70 (ponto doce)
- **Catalisador** (0-10 pts): noticias ou eventos positivos

### Paper Trading: simulacao sem dinheiro real

Paper Trading e o modo "faz de conta". Tudo funciona como se fosse dinheiro real, mas e simulacao. O sistema:

1. Gera sinais de compra e venda baseados nos especialistas
2. Mantem um portfolio simulado com saldo inicial
3. Calcula lucros, perdas, e estatisticas
4. **NUNCA envia ordens para corretoras reais** (a menos que voce explicitamente mude a configuracao de seguranca -- e isso esta bloqueado por padrao)

Quando voce ve "IBKR PAPER CONNECTED" na barra de status, significa que o SuperEzio esta conectado ao simulador da Interactive Brokers (modo paper). Nao e dinheiro real.

**Regra pratica:** enquanto o modo estiver como "SNAPSHOT" ou "PAPER", voce pode testar a vontade sem risco.

---

## 3. Como fazer sua primeira analise

### Analise rapida de uma acao

1. Abra o SuperEzio no navegador (http://localhost:8002)
2. No campo de busca no topo, digite o ticker (ex: "AAPL", "PETR4", "MGLU3")
3. Pressione Enter -- o grafico carrega com as velas
4. No canto inferior direito, clique no icone do Bob (icone de mensagem) para abrir o chat
5. Digite: "Analisa essa acao para mim"
6. O Bob vai processar e mostrar:
   - O veredito de cada especialista
   - As barras de confianca
   - Um resumo em texto explicando a situacao
   - Se vale ou nao a pena arriscar

### Ver oportunidades do Mangala

No chat com Bob, pergunte:
- "Tem alguma penny stock interessante hoje?"
- "Mostra as oportunidades do Mangala"

O sistema vai escanear e mostrar as melhores opcoes com seus scores.

### Simular uma operacao

As operacoes no Paper Trading sao geradas automaticamente quando os especialistas chegam a um consenso positivo. Voce pode ver as ordens simuladas na area "ORDERS & POSITIONS" abaixo do grafico.

Para ver a fila de aprovacao, abra o "Ops Console" (icone de terminal na barra superior).

---

## 4. Como interpretar os cards

### Card F51 -- Exemplo:

```
+----------------------------------------------------+
| [F51] Veracity Consensus               [87%]    [X] |
|                                                    |
|            ╭──────────╮                            |
|            │   87%    │   <-- gauge circular       |
|            ╰──────────╯                            |
|                                                    |
| Veracity    ████████████░░░░  87%                  |
| Consensus   ██████████░░░░░░  65%                  |
| Proxy Reward████████████████  100%                 |
| Robustness  ████████░░░░░░░░  52%                  |
| Uncertainty ██░░░░░░░░░░░░░░  12%                  |
| Danger      █░░░░░░░░░░░░░░░   8%                  |
|                                                    |
| Hub Risk    ████████░░░░░░░░  48%                  |
+----------------------------------------------------+
```

- **87%** (gauge) = nota geral. Acima de 70% e bom. Entre 40-70% requer cautela. Abaixo de 40% e vermelho.
- **Veracity** = o quanto os dados sao confiaveis
- **Consensus** = nivel de concordancia entre os especialistas
- **Uncertainty** = o quanto o sistema nao tem certeza (menor e melhor)
- **Danger** = nivel de perigo (menor e melhor)
- **Hub Risk** = risco geral do ativo no mercado

### Card SDCA -- Exemplo:

```
+----------------------------------------------------+
| [SDCA] Risk Firewall                   [ALLOW]  [X] |
|                                                    |
| Bloqueios: nenhum                                  |
| Fatores de risco avaliados:                         |
|   - FOMO: nao detectado                            |
|   - Alavancagem: conservadora                      |
|   - Slippage: baixo                                |
|   - Dados: qualidade alta                          |
+----------------------------------------------------+
```

O veredito pode ser:
- **ALLOW** (verde) = risco aceitavel
- **BLOCK** (vermelho) = risco alto, operacao barrada
- **Caution** (amarelo) = atencao, mas nao bloqueado

### Card NRL (Neural) -- Exemplo:

```
+----------------------------------------------------+
| [NRL] Neural Prediction                [ALTA]   [X] |
|                                                    |
| Direcao esperada:                                  |
|   Alta:    ████████████░░░░░  68%                  |
|   Baixa:   ████░░░░░░░░░░░░░  18%                  |
|   Lateral: ████░░░░░░░░░░░░░  14%                  |
|                                                    |
| Confianca: ALTA  |  Risco de cauda: BAIXO          |
+----------------------------------------------------+
```

### Card TRI (Trinity) -- Exemplo:

```
+----------------------------------------------------+
| [TRI] Trinity Deliberation           [SUPPORT]  [X] |
|                                                    |
| Decisao final da equipe de analistas                |
| Pontuacao: moderada positiva                        |
+----------------------------------------------------+
```

Verditos:
- **SUPPORT** = a equipe apoia a operacao
- **BLOCK** = a equipe recomenda nao entrar
- **NEUTRAL** = nao ha conviccao suficiente

### Card GRD (Guardrails) -- Exemplo:

```
+----------------------------------------------------+
| [GRD] Guardrail Hub                     [28/30] [X] |
|                                                    |
| L1 Input Security  (4/4) ✓                          |
| L2 Provider        (3/3) ✓                          |
| L3 Data Quality    (3/4) ⚠                          |
| L4 Risk Analysis   (4/4) ✓                          |
| ...                                                 |
+----------------------------------------------------+
```

A pontuacao e X/30. Acima de 25 e seguro. Entre 20-25 requer atencao. Abaixo de 20 e critico.

---

## 5. FAQ

### "O Bob e confiavel?"

O Bob e uma ferramenta de analise, nao um consultor financeiro registrado. Ele:
- Usa dados reais de mercado (precos, volumes, noticias)
- Consulta especialistas deterministicos (numeros, nao palpites)
- Mostra explicitamente seu nivel de confianca em cada fator

Porem, ele:
- NAO sabe o futuro
- NAO conhece sua situacao financeira pessoal
- NAO substitui uma analise propria ou consultoria profissional

Use o Bob como um assistente que organiza informacao, nao como uma fonte unica de verdade.

### "Posso usar com dinheiro real?"

**Nao, a menos que voce mude configuracao explicita de seguranca.**

Por padrao, o SuperEzio opera em modo PAPER (simulacao):
- Nenhuma ordem e enviada para corretoras reais
- O botao "IBKR" mostra a conexao com o simulador da Interactive Brokers
- O status "SNAPSHOT" na barra superior indica que nao ha conexao ao vivo

Para operar com dinheiro real, voce precisaria:
1. Configurar manualmente as variaveis de ambiente de seguranca
2. Conectar a uma conta real de corretora
3. Assumir total responsabilidade pelos resultados

**O sistema e fornecido "como esta", sem garantia de lucro. Nao invista dinheiro que voce nao pode perder.**

### "O SuperEzio opera automaticamente?"

Nao. O sistema gera analises e recomendacoes, mas toda decisao de executar uma ordem passa por um "gate de aprovacao" que requer revisao humana. Mesmo em modo paper, operacoes acima de um certo valor (padrao: US$ 500 de risco) precisam de confirmacao manual.

### "Precisa de internet?"

Sim. O SuperEzio baixa dados de precos da internet (fontes como Yahoo Finance). Sem internet, o grafico nao carrega e as analises ficam limitadas.

### "Funciona no celular?"

O layout funciona em navegadores de celular, mas a experiencia e melhor em desktop (a tela e grande e tem muitos elementos lado a lado).

### "Quais mercados cobre?"

Cobertura primaria: acoes dos EUA e Canada. Outros mercados (Brasil, Europa, Asia) podem ter dados menos completos ou indisponiveis dependendo da fonte.

### "Precisa de placa de video (GPU)?"

A interface grafica (grafico de velas) funciona no navegador e nao precisa de GPU especial.

O modelo de linguagem (o "cerebro" do Bob) PODE usar GPU se voce tiver uma placa NVIDIA com pelo menos 8 GB de VRAM, mas tambem funciona so no processador (CPU). Na CPU, as respostas podem demorar de 30 segundos a 2 minutos.

### "O que significa 'IBKR' na barra?"

O botao IBKR mostra a conexao com a Interactive Brokers (modo paper trading). Se estiver verde, esta conectado ao simulador. Se estiver cinza/offline, nao ha conexao. Mesmo conectado, e PAPEL -- sem dinheiro real.

### "E seguro?"

O sistema tem multiplas camadas de seguranca internas (Guardrail Hub). Entre elas:
- Validacao de dados de entrada
- Controle de qualidade dos dados de mercado
- Auditoria de todas as decisoes
- Firewall de risco (SDCA)
- Gatilho de parada de emergencia (kill switch)
- Modo "live" desligado por padrao

---

## 6. Troubleshooting

### "O grafico nao aparece"

- Verifique se o servidor esta rodando (`python -m agent_server.main`)
- Abra o console do navegador (F12) e veja se ha erros em vermelho
- Tente digitar um ticker diferente (ex: "AAPL")
- Verifique se voce tem internet

### "Bob nao responde"

- As respostas do Bob levam de 30 segundos a 2 minutos (ele processa muitos dados)
- Verifique se o servidor esta rodando
- Se o servidor de AI (llama-server na porta 8082) nao estiver rodando, o Bob funciona em modo limitado
- Tente perguntar algo mais especifico

### "Erro 'Porta ja em uso'"

Outro programa ja esta usando a porta 8002 ou 8082. No Windows, execute `stop.ps1` para liberar as portas.

### "Nao consigo digitar tickers brasileiros"

Tickers brasileiros na B3 tem formato especifico (ex: "PETR4", "VALE3", "MGLU3"). Se nao funcionar, tente buscar pelo codigo americano equivalente (ex: "PBR" para Petrobras, "VALE" para Vale).

### "Os numeros dos especialistas estao diferentes"

Cada especialista pode ter opinioes diferentes -- isso e normal. O Trinity (TRI) e quem tenta chegar a um consenso final. Divergencia entre especialistas e um sinal de que o ativo e controverso e merece cautela extra.

### "A tela esta muito lenta"

- Feche outras abas pesadas no navegador
- Nao abra varias janelas do SuperEzio ao mesmo tempo
- Reduza o timeframe (use 1M ou 3M em vez de 5Y)
- Em maquinas mais antigas, o grafico WebGL pode ficar pesado

### "Quero comecar do zero (reset)"

Os dados de analise e historico ficam na pasta `data/`. Voce pode apagar ou renomear a pasta `data/` com o sistema desligado para comecar de um estado limpo. As configuracoes ficam no arquivo `.env.local`.

---

## Aviso final

**SuperEzio nao e uma recomendacao de investimento. E uma ferramenta de analise.**

A responsabilidade por qualquer decisao financeira e sempre sua. Use o SuperEzio para se informar, aprender e testar estrategias -- mas nunca invista dinheiro baseado apenas em uma ferramenta automatizada.

> "Confie, mas verifique."
