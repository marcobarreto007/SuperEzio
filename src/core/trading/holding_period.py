"""Mapa semantico de `expected_holding_period` -> horizonte vertical (barras/dias).

Por que este modulo existe
--------------------------
`PaperTrade.expected_holding_period` (paper_journal.py:97) e uma string de PRODUTO
("day_trade" | "swing" | "position" | "long_term") -- quem escreve e o agente, nao o
mercado. O labeler de barreira tripla, por outro lado, so entende o inteiro
`time_horizon_bars` (a barreira vertical de Lopez de Prado). Nenhuma biblioteca de
triple barrier faz essa ponte: nao ha "swing" em AFML. E semantica de produto e por
isso mora aqui, escrita a mao, com tabela explicita e teste.

Ancora no proprio repositorio
-----------------------------
`feedback_loop.py:184-188` ja classifica o holding REALIZADO de cada trade fechado:
`< 24h` -> day_trade, `< 7 dias` -> swing, senao position. A tabela abaixo e
deliberadamente compativel com essa classificacao -- o horizonte que se promete na
abertura e do mesmo tamanho da faixa em que o trade vai ser contabilizado depois.

Por que o limite INFERIOR de cada faixa (e nao o superior)
----------------------------------------------------------
Barreira vertical e um corte a favor do pessimismo: quando ela dispara, o trade e
fechado a mercado e o resultado entra em `outcome_learning.py`. Escolher o limite
INFERIOR de cada faixa encurta a janela -> o trade e cortado mais cedo -> menos
exposicao a deriva de mercado e menos chance de um resultado bom ser sorte de tempo,
nao tese. O custo aceito e cortar alguns vencedores lentos: e o lado certo para errar
num journal que alimenta aprendizado.

Como ler `bars` e `calendar_days`
---------------------------------
`bars` e o que o labeler consome e e contado em BARRAS DO TIMEFRAME AVALIADO. Todos os
providers deste repositorio (yfinance/akshare/finnhub/twelve_data) entregam candle
DIARIO, entao hoje 1 barra == 1 dia de pregao. Se um timeframe intradiario for ligado
no futuro, `bars` continua correto (e o que a barreira usa) mas `calendar_days` deixa
de valer -- ele assume pregao diario.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)

# Numero de dias de pregao numa semana. Usado so para converter barras diarias em
# dias de calendario (a barreira vertical conta BARRAS, nao dias corridos).
TRADING_DAYS_PER_WEEK = 5


# Tabela canonica: faixa de produto -> numero de barras diarias.
#
#   day_trade :  1 barra   (1 dia de pregao)   -- o menor horizonte que existe sem
#                            candle intradiario; este repositorio nao tem pipeline
#                            intradiario, entao 1 e o piso real, nao uma escolha.
#   swing     :  5 barras  (1 semana)          -- limite INFERIOR da faixa swing de
#                            feedback_loop.py:186 (que vai ate 7 dias). Prometer 5 e
#                            ser contabilizado em "swing" ficam consistentes.
#   position  : 21 barras  (1 mes)             -- limite inferior do que ja e "position"
#                            naquela classificacao (> 7 dias); 21 dias de pregao e o
#                            mes convencional de mercado.
#   long_term : 63 barras  (1 trimestre)       -- menor horizonte que o mercado chama de
#                            longo prazo em dias de pregao.
HOLDING_PERIOD_BARS: dict[str, int] = {
    "day_trade": 1,
    "swing": 5,
    "position": 21,
    "long_term": 63,
}

# Fallback para string ausente/desconhecida. E "swing" porque e o unico valor que a
# producao realmente grava: `auto_execute_paper.py:755` e `:865` passam
# `expected_holding_period="swing"` fixo. Qualquer linha do journal sem o campo veio
# desses dois caminhos.
DEFAULT_HOLDING_PERIOD = "swing"


def normalize_holding_period(period: object) -> str:
    """Normaliza a string de produto para uma chave de `HOLDING_PERIOD_BARS`."""
    token = str(period or "").strip().lower().replace("-", "_").replace(" ", "_")
    return token or DEFAULT_HOLDING_PERIOD


def holding_period_bars(period: object) -> int:
    """Barras do horizonte vertical para um `expected_holding_period`.

    Valor desconhecido NAO levanta: cai no default conservador e loga, porque uma
    linha antiga do journal com texto livre (`"unknown"`, `""`) nao pode travar o
    fechador em producao.
    """
    token = normalize_holding_period(period)
    bars = HOLDING_PERIOD_BARS.get(token)
    if bars is None:
        logger.warning(
            "holding_period_unknown_fallback period=%r fallback=%s",
            period,
            DEFAULT_HOLDING_PERIOD,
        )
        bars = HOLDING_PERIOD_BARS[DEFAULT_HOLDING_PERIOD]
    return bars


def holding_period_days(period: object) -> int:
    """Dias de CALENDARIO equivalentes, assumindo candle diario (5 dias uteis/semana)."""
    return bars_to_calendar_days(holding_period_bars(period))


def bars_to_calendar_days(bars: int) -> int:
    """Converte barras diarias em dias de calendario, arredondando para cima.

    Cima, nao baixo: a barreira vertical so pode disparar num dia de pregao, entao o
    prazo em calendario tem que cobrir a ultima barra -- arredondar para baixo
    prometeria um prazo que o mercado nao entrega.
    """
    if bars <= 0:
        return 0
    return math.ceil(bars * 7 / TRADING_DAYS_PER_WEEK)


def holding_period_horizon(period: object) -> dict[str, int | str]:
    """Forma serializavel do mapa, para persistir ou logar junto da abertura."""
    token = normalize_holding_period(period)
    if token not in HOLDING_PERIOD_BARS:
        token = DEFAULT_HOLDING_PERIOD
    bars = HOLDING_PERIOD_BARS[token]
    return {
        "expected_holding_period": token,
        "time_horizon_bars": bars,
        "time_horizon_days": bars_to_calendar_days(bars),
    }
