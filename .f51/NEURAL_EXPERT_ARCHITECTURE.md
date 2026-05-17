# F51 Architecture: Technical Neural Expert Node

## 1. A Visão: O que é o Neural Expert?
Em vez de depender apenas de indicadores estáticos (RSI cru, médias móveis), vamos construir um nó no grafo que se comporta como uma **Rede Neural Dinâmica**. Ele recebe os dados de preço (OHLCV) do `DataCollector`, treina um mini-modelo (MLP ou LSTM) *on-the-fly* usando as últimas 600 barras daquele ativo específico, e tenta prever o movimento das próximas N barras. 
O output desse Expert não é "Compre" ou "Venda", mas sim um **Tensor de Probabilidade Técnica** (ex: `0.82` de chance de alta).

## 2. Onde ele entra no Pipeline F51?
O pipeline atual é assim:
`User` ➔ `Orchestrator` ➔ `DataCollector` ➔ `PennyLab/MathCore` ➔ `CEO (LLM)`

O **Neural Expert** entra em paralelo aos avaliadores quantitativos, antes da decisão final:
`DataCollector` ➔ **[ Technical Neural Expert ]** ➔ `MathCore` (Para calcular o tamanho da aposta) ➔ `CEO (LLM)`

**Impacto Arquitetural:** O CEO deixa de ler o RSI cru e passa a receber um laudo mastigado: *"O Neural Expert treinou uma rede LSTM com as últimas 600 barras, validou com os últimos 100 dias (holdout split) e projeta uma probabilidade de 74% de alta amanhã com base na microestrutura de preço."*

## 3. Como Construir Nós Mesmos (O Backend Python)
No TradingView, o NeuraLib pena com limites de processamento. No nosso backend Python, nós somos deuses do processamento local.
- **Framework:** Usaremos PyTorch leve (`torch.nn`) ou Scikit-Learn.
- **Pipeline de Dados Automático:** Quando o `DataCollector` baixar o histórico do Yahoo Finance, o nó vai normalizar os dados (Z-Score) internamente.
- **Topologia:** Uma rede neural simples Sequencial (Dense ➔ Dropout ➔ Dense ➔ ReLU) usando o otimizador AdamW e perda de Huber, idêntica ao NeuraLib, mas rodando em milissegundos na nossa máquina.
- **Output:** O nó retorna um dicionário para o State do Grafo: `{"neural_score": 0.85, "confidence": 0.90, "loss_convergence": "stable"}`.

---

## 4. Reflexão Prática: 10 Cenários Simulados

O impacto real de ter esse nó aparece quando a Rede Neural discorda ou confirma os outros especialistas. Veja as dinâmicas de conflito e resolução pelo CEO:

### Cenário 1: A Faca Caindo (Falso Fundo)
- **Ação:** Despencou 40% em um dia. O RSI está em 15 (Sobrevendido).
- **Neural Expert:** Avalia a matriz e vê que a velocidade da queda rompeu o desvio padrão. Output: **0.15 (Venda Forte/Crash)**.
- **CEO Verdict:** O CEO ignora a ilusão do indicador cru (RSI baixo) porque o Neural Expert detectou anomalia estrutural. **AVOID.**

### Cenário 2: O Pump Sem Liquidez (Penny Stock Trap)
- **Ação:** Subindo 200%.
- **Neural Expert:** O modelo técnico enxerga um padrão claro de continuação. Output: **0.90 (Compra)**.
- **PennyLab / MathCore:** Detectam que a liquidez é minúscula e o risco de deslistagem (TSX-V) é extremo.
- **CEO Verdict:** "A técnica é de compra, mas o risco de contraparte é insustentável." **REJECTED.**

### Cenário 3: O Breakout Perfeito
- **Ação:** Consolidação de 6 meses rompendo resistência.
- **Neural Expert:** O modelo detecta a compressão de volatilidade e projeta explosão. Output: **0.88 (Compra)**.
- **MathCore:** Risco controlado, CVaR favorável.
- **CEO Verdict:** Convergência total. O CEO autoriza a compra e o MathCore calcula alocação de Kelly máxima. **STRONG BUY.**

### Cenário 4: Choque de Notícias (FDA Approval)
- **Ação:** Empresa pharma aprova remédio surpresa. Preço dispara no pre-market.
- **Neural Expert:** Como treina apenas no passado gráfico, a rede neural fica confusa ou atrasada. Output: **0.50 (Neutro)**.
- **Sentiment/RAG:** Alerta máximo de catalisador positivo (News: Bullish).
- **CEO Verdict:** O CEO pondera: a técnica está neutra porque a estrutura mudou hoje, mas o fundamento mudou. **BUY (News-Driven).**

### Cenário 5: Armadilha de Urso (Bear Trap)
- **Ação:** Perde um suporte óbvio de varejo, mas entra volume institucional oculto.
- **Neural Expert:** O modelo matricial detecta divergência oculta entre Preço e Momentum que o olho humano não vê. Output: **0.75 (Compra/Reversão)**.
- **CEO Verdict:** O CEO confia na leitura não-linear da rede e entra comprando na armadilha contra o varejo.

### Cenário 6: Mercado Lateral (Choppy)
- **Ação:** Andando de lado sem direção há semanas.
- **Neural Expert:** A rede treina, mas a função de perda (Loss) não converge bem. A confiança do modelo cai. Output: **0.49 a 0.51**.
- **CEO Verdict:** "O Neural Expert relata incapacidade de encontrar borda matemática na matriz atual. Fique fora até a expansão de volatilidade." **WAIT.**

### Cenário 7: Grind Lento (Tendência Institucional)
- **Ação:** Subindo 0.5% ao dia, todos os dias, sem volatilidade.
- **Neural Expert:** LSTMs adoram isso. Output: **0.80 (Tendência Forte)**.
- **MathCore:** O VaR é baixíssimo.
- **CEO Verdict:** O CEO aloca uma posição pesada, segura e de baixa manutenção, surfando a inércia algorítmica.

### Cenário 8: Adaptação de Ativo Descorrelacionado (Cripto vs Milho)
- **Situação:** Como a rede neural treina *on-the-fly* para CADA ativo que você pede, os pesos do modelo se adaptam à "personalidade" do ativo. 
- **Impacto:** O Neural Expert será excelente para prever Bitcoin (alta volatilidade) E Milho (sazonal), pois os pesos são forjados no momento da requisição usando os dados do próprio ativo.

### Cenário 9: Mudança de Regime Macro
- **Ação:** O FED sobe juros de surpresa.
- **Neural Expert:** Nos primeiros dias, o modelo técnico falha (erro de predição aumenta vertiginosamente).
- **Orquestrador:** Nota a queda de acurácia em tempo real e diminui o peso de confiança do Neural Expert até que ele seja retreinado com a nova estrutura de mercado.

### Cenário 10: Saturação de Momentum
- **Ação:** Ativo já subiu 500%.
- **Neural Expert:** A rede tenta projetar os alvos, mas a ativação (Dropout/Regularização) nota que o risco de Overfitting no movimento esticado é brutal. Output: **0.20 (Exaustão/Reversão)**.
- **CEO Verdict:** O CEO manda realizar lucros antes da reversão brusca, protegendo o caixa.

## Conclusão de Engenharia
Ter uma Rede Neural Dinâmica avaliando o preço e enviando um *Tensor Score* para um LLM institucional é o Santo Graal do trading quantitativo. O LLM fornece a lógica de negócios e blindagem macro, enquanto o Neural Expert faz o trabalho sujo de microestrutura não-linear que o LLM é incapaz de fazer sozinho.
