"""Barreira tripla: primeiro toque de stop / alvo / prazo, com motivo.

===============================================================================
MIT License

Copyright (c) 2025-2026 Stefan Jansen          <- FONTE PRIMARIA (ml4t/engineer)
Copyright (c) 2024, Robert Bach                <- linhagem (mlfinpy, via AFML)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
===============================================================================

QUAL FONTE FOI PORTADA, E POR QUE (declarado, conforme exigido pela licenca acima)
---------------------------------------------------------------------------------
FONTE PRIMARIA: `ml4t/engineer` -- `src/ml4t/engineer/labeling/triple_barrier.py` e
`.../labeling/numba_ops.py`
(https://github.com/ml4t/engineer, MIT, (c) 2025-2026 Stefan Jansen; ultimo push
2026-09-10). Deste vieram as REGRAS DE DECISAO intrabar: toque por high/low, desempate
pessimista no stop e preenchimento pelo `open` quando a barra abre atravessando o
nivel (`_check_barrier_touch` / `_resolve_barrier_exit`).

LINHAGEM ALGORITMICA: `mlfinpy/labeling/labeling.py::triple_barriers`
(https://github.com/baobach/mlfinpy, MIT, (c) 2024 Robert Bach), que implementa o
"Snippet 3.2, page 45" de Marcos Lopez de Prado, "Advances in Financial Machine
Learning" (Wiley, 2018), Cap. 3 "Labeling". Deste veio o tratamento da BARREIRA
VERTICAL (horizonte `t1` consumido sem toque horizontal: saida no fechamento da
ultima barra do prazo).

Por que o ml4t ganhou do mlfinpy como fonte primaria: o mlfinpy avalia a serie de
`close` e nao enxerga toque intrabar -- as tres adaptacoes que este projeto exige
(high+low, stop primeiro no empate, gap pelo open) teriam que ser INVENTADAS aqui. O
ml4t ja as implementa, de forma independente e com o mesmo sinal pessimista
(`if lower_hit: return -1` vem antes de `if upper_hit`). Ou seja: copiar a regra de
quem ja a escreveu certo e exatamente o que a regra 1 do projeto pede. O texto dos
dois copyrights acima e o original e nao foi alterado.

O que NAO foi portado do ml4t: `polars`, `numba`/`@jit` e `trailing_stop`. O ml4t exige
`requires-python >=3.12` + polars + numba; este repositorio esta em Python 3.11 e nao
tem nenhuma das duas. Nada disso e necessario para a decisao: a implementacao abaixo e
sequencial, sobre `Sequence[Mapping]`, e importa somente `math` e `dataclasses`.

DIVERGENCIAS DELIBERADAS DESTE PORTE (onde o ml4t faz diferente)
---------------------------------------------------------------
(a) **Alvo tocado por gap NAO e preenchido pelo `open`.** O ml4t faz
    `if open_price >= upper_price: return 1, open_price` -- num gap de alta o alvo
    realiza MAIS que o nivel, o que e realista mas e otimista. Aqui o alvo preenche no
    proprio nivel, limitado a faixa da barra (`max(low, min(high, target))` para
    longo). DECISAO DO PROJETO: no lado do GANHO nao se maquia para cima. O gap so
    melhora o preenchimento no lado do STOP, onde a regra pessimista e obrigatoria.
(b) **Clamp na faixa da barra.** O ml4t devolve o nivel cru; aqui o preenchimento e
    limitado a [low, high], porque preco fora do range do candle nao existe.
(c) **Sem `trailing_stop`, sem barreira simetrica (`side == 0`) e sem pesos de
    unicidade.** O protocolo deste repositorio opera direcional com stop e alvo
    persistidos na abertura; trailing stop mudaria a regra de risco sem decisao do
    operador.
(d) **Desempate documentado como decisao de produto**, nao como detalhe de
    implementacao -- ver item 2 abaixo.

As demais adaptacoes sao deliberadas e estao listadas uma a uma:

1. **High e low, nao so close.** No mlfinpy o defeito e justamente este: ele avalia a
   serie de CLOSE (`close[loc:vertical_barrier]`) e perde todo toque intrabar. Aqui
   cada barra e avaliada pela sua faixa [low, high], que e onde um stop ou alvo
   realmente executa -- mesma escolha do ml4t (`_check_barrier_touch`). `close`
   continua sendo usado apenas no desfecho de prazo (barreira vertical), que e onde o
   mlfinpy tambem para.

2. **Desempate: STOP primeiro.** Ninguem resolve isto de forma consensual na
   literatura, mas a unica implementacao mantida que ENCONTRA este caso o resolve
   assim: o ml4t comenta "OHLC data does not reveal which intrabar extreme occurred
   first. Resolve dual touches conservatively as a stop loss." e devolve -1 (stop)
   antes de testar o alvo. O projeto adota a mesma regra por conta propria, e pelo
   mesmo motivo: e pessimista, e este journal alimenta `outcome_learning.py` -- nao se
   maquia resultado para cima. Documentado tambem em `evaluate_triple_barrier`.

3. **Gap de abertura.** Se o nivel do stop esta FORA da faixa da barra (a barra
   inteira ficou do outro lado do stop), houve gap de abertura: o preenchimento e pelo
   `open`, que e o pior preco daquele lado. Se o nivel esta DENTRO da faixa, preenche
   pelo proprio nivel. Clamp: longo `max(low, stop)`, curto `min(high, stop)` -- o
   preenchimento nunca sai do range do candle. Mesma regra do ml4t
   (`if open_price <= stop_price: return -1, open_price`) e mesma regra de mercado que
   o freqtrade implementa sob GPL-3.0; nenhuma linha do freqtrade foi lida ou copiada
   -- a regra foi tomada do ml4t, que e MIT. Ver `_fill_price`.

4. **Motivo no vocabulario do journal.** O original devolve so timestamps (`pt`/`sl`)
   e cabe ao chamador decidir o rotulo. Aqui o resultado ja carrega
   `exit_reason` em `{"take_profit", "stop_loss", "time_exit"}` -- o subconjunto dos
   motivos validos de `paper_journal.py:118-120` que a barreira tripla sabe produzir.

5. **SEM multiprocessamento.** O original expoe `num_threads` e delega para
   `mlfinpy/util/multiprocess.py::mp_pandas_obj`, que abre um `mp.Pool` quando
   `num_threads != 1`. Aquele modulo NAO tem `if __name__ == "__main__"` nem
   `freeze_support()`; no Windows, criar o Pool a partir de um processo ja inicializado
   (o nosso caso: o heartbeat dentro do app) arrisca re-import e travamento. O caminho
   sequencial (`num_threads=1`) e o unico seguro e e o UNICO portado aqui: por
   construcao este modulo nao tem parametro de paralelismo e nunca abre processo.
   Isso tambem mantem o modulo importavel so com stdlib (`math` + `dataclasses`).
   Pelo mesmo motivo nao se portou o `@jit(nopython=True)` do ml4t: aqui e Python puro.

6. **Barreira por PERCENTUAL, nao por ATR -- decisao consciente, nao omissao.**
   O ml4t tem `atr_barriers.py` (barreiras por multiplo de ATR, que se alargam em
   regime volatil e se estreitam em regime calmo) e a ideia e boa para ETF, que tem
   volatilidade muito diferente por setor e por regime. NAO foi adotada AGORA, por
   tres razoes:
     - Este modulo nao decide como a barreira nasce, so como ela e AVALIADA: ele recebe
       niveis ABSOLUTOS de preco. Trocar percentual por ATR e mudar `build_barriers`
       (meta_labeling.py:88), que alimenta o gate `evaluate_meta_labeling_gate` com
       requisito normativo de assimetria 2,5:1 e tem testes proprios. Sao duas
       mudancas de risco diferente; misturar as duas num diff so nao cabe em revisao.
     - O ATR que alimentaria a barreira (`atr_14`) vem do `math_report`, que existe no
       caminho completo do pipeline e NAO esta garantido no ponto de abertura
       (`auto_execute_paper.py`). Uma barreira que nao pode ser construida sem a feature
       precisa de fallback de qualquer forma, e o fallback e o percentual -- entao o
       percentual continua sendo o piso.
     - O journal atual e 100% sintetico (ver `.claude/agent-memory/causa-raiz/
       paper-journal-100-por-cento-contaminado.md`): nao existe amostra real para dizer
       se a barreira por ATR melhora ou piora ESTE ativo. Trocar por ATR hoje seria
       trocar por sensacao, e o ganho citado no ml4t (Sharpe 0,85 -> 1,45 em SPY
       2010-2024) e de backtest de TERCEIRO, nao medido aqui.
   Caminho de adocao futura, quando houver journal real: implementar a construcao ATR
   em `build_barriers` e persistir os mesmos tres campos (`stop_loss_price`,
   `take_profit_price`, `time_horizon_bars`). Este evaluator nao muda uma linha --
   e exatamente por isso que ele foi desenhado sobre niveis absolutos.

Fora de escopo, de proposito (nao portado, e nao e bug deste modulo):
    - **Correcao sobre o ml4t:** la o toque horizontal tambem e procurado dentro do
      horizonte, mas o laco so roda com a janela completa. Aqui a busca cobre as
      barras disponiveis mesmo antes do prazo: fechar um trade que JA bateu o stop
      nao pode esperar o horizonte inteiro terminar.

    - `CombinatorialPurgedKFold` do mlfinpy tem embargo zerado a cada iteracao
      (`self.embargo = 0` antes de `delta * self.embargo`). Nao foi trazido. Se
      validacao cruzada purgada for necessaria, a escolha e o pacote `purgedcv` (MIT),
      ainda nao instalado.
    - `add_vertical_barrier`, `get_events` e `get_bins` do original operam sobre
      `pd.Series`/`pd.DataFrame` de eventos e volatilidade alvo; o fechador deste
      repositorio avalia UM trade por vez a partir das barreiras ja persistidas, e
      `build_barriers` (meta_labeling.py:88) ja cobre a construcao das barreiras.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# Vocabulario identico ao de `paper_journal.py:118-120` (motivos validos de saida).
STOP_LOSS = "stop_loss"
TAKE_PROFIT = "take_profit"
TIME_EXIT = "time_exit"

# Motivos que a barreira tripla sabe produzir (subconjunto do vocabulario do journal).
BARRIER_EXIT_REASONS: frozenset[str] = frozenset({STOP_LOSS, TAKE_PROFIT, TIME_EXIT})

_LONG_SIDES = frozenset({"LONG", "BUY", "BULLISH"})
_SHORT_SIDES = frozenset({"SHORT", "SELL", "BEARISH"})


@dataclass(frozen=True)
class BarrierTouch:
    """Desfecho do primeiro toque: qual barreira, a que preco, depois de quantas barras."""

    exit_reason: str  # "stop_loss" | "take_profit" | "time_exit"
    exit_price: float
    exit_index: int  # offset (0-based) da barra do toque, DENTRO da janela avaliada
    bars_held: int  # 1-based: quantas barras foram consumidas ate o toque
    gapped: bool  # True quando o stop foi preenchido pelo open (gap de abertura)
    exit_timestamp: str | None = None

    @property
    def touched_stop(self) -> bool:
        return self.exit_reason == STOP_LOSS

    @property
    def is_profit(self) -> bool:
        """Y=1 de AFML: o alvo foi tocado antes do stop e antes do prazo."""
        return self.exit_reason == TAKE_PROFIT

    def to_binary_label(self) -> int:
        """Rotulo binario da meta-labeling (AFML cap. 3): 1 = alvo, 0 = resto.

        Alvo OU qualquer outra coisa (stop ou prazo) -- um trade que venceu por
        prazo nao e "sucesso do sinal", e sim ausencia de falha, e por isso cai em 0.
        """
        return 1 if self.is_profit else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_reason": self.exit_reason,
            "exit_price": round(self.exit_price, 6),
            "exit_index": self.exit_index,
            "bars_held": self.bars_held,
            "gapped": self.gapped,
            "exit_timestamp": self.exit_timestamp,
            "label": self.to_binary_label(),
        }


def normalize_side(side: object) -> str:
    """Normaliza o lado para "long" | "short"."""
    token = str(side or "").strip().upper()
    if token in _LONG_SIDES:
        return "long"
    if token in _SHORT_SIDES:
        return "short"
    raise ValueError(f"Unrecognized side for barrier evaluation: {side!r}")


def _bar_fields(bar: Mapping[str, Any]) -> tuple[float, float, float, float, str | None]:
    """Extrai (open, high, low, close, timestamp) de uma barra OHLCV.

    Fallback deliberado: sem `high`/`low` a barra regride ao comportamento do
    mlfinpy original (tudo igual ao close). Isso mantem o modulo utilizavel com
    series de fechamento puras -- o que perde e o toque intrabar, nao a corretude.
    """
    close = _as_float(bar.get("close"))
    if close is None:
        raise ValueError(f"Bar without a usable close price: {bar!r}")
    open_ = _as_float(bar.get("open"))
    high = _as_float(bar.get("high"))
    low = _as_float(bar.get("low"))
    # Sem open valido, o open mais honesto e o proprio close: assume que a barra
    # nao abriu longe de onde fechou (e nao inventa um gap).
    if open_ is None:
        open_ = close
    if high is None:
        high = close
    if low is None:
        low = close
    # Coerencia OHLC: um provider pode devolver high < low numa barra corrompida.
    # Corrigir e mais barato que propagar um toque impossivel.
    high = max(high, open_, low, close)
    low = min(low, open_, high, close)
    timestamp = bar.get("datetime") or bar.get("observed_at") or bar.get("date")
    return open_, high, low, close, (str(timestamp) if timestamp else None)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _epsilon(level: float) -> float:
    """Tolerancia relativa para comparar nivel e preco sob ruido de float.

    O stop deste projeto e calculado multiplicativamente (`entry * (1 - pct)`), entao
    um toque EXATO no nivel vira `95.00000000000001` vs `95.0` e um `<` cru perde o
    toque. A tolerancia e so de precisao de float, nao de mercado.
    """
    return 1e-9 * max(1.0, abs(level))


def _fill_price(*, side: str, level: float, open_: float, high: float, low: float) -> float:
    """Preco de preenchimento de um nivel dentro de uma barra (adaptacao 3).

    Regra do gap (reimplementada, nao copiada do freqtrade):
      - nivel do stop FORA da faixa da barra -> a barra inteira ficou do outro lado
        do stop, ou seja houve gap de abertura: preenche pelo `open`, que e o pior
        preco da barra naquele lado -- exatamente o que acontece de verdade.
      - nivel DENTRO da faixa -> preenche pelo proprio nivel.

    Clamp final: o preenchimento nunca sai da faixa da barra (longo `max(low, ...)`,
    curto `min(high, ...)`), porque preco fora do range do candle nao existe.
    """
    if side == "long":
        if level > high + _epsilon(level):
            return open_  # gap de abertura para baixo, atravessou o stop
        return max(low, min(high, level))
    if level < low - _epsilon(level):
        return open_  # gap de abertura para cima, atravessou o stop
    return min(high, max(low, level))


def evaluate_triple_barrier(
    bars: Sequence[Mapping[str, Any]],
    *,
    side: object,
    stop_loss_price: float,
    take_profit_price: float,
    time_horizon_bars: int,
    start_index: int = 0,
) -> BarrierTouch | None:
    """Primeiro toque entre stop, alvo e prazo, com o motivo do desfecho.

    Parametros
    ----------
    bars : sequencia de barras OHLCV (dicts com open/high/low/close e, de preferencia,
        `datetime`). Aceita qualquer sequencia indexavel -- o fechador passa a lista
        de candles do `DataHub`.
    side : "long"/"short" (aceita BUY/SELL/LONG/SHORT).
    stop_loss_price, take_profit_price : niveis ABSOLUTOS de preco persistidos na
        abertura do trade (ver `paper_journal` e `meta_labeling.build_barriers`).
    time_horizon_bars : barreira vertical, em barras da serie avaliada.
    start_index : primeira barra a avaliar. O fechador passa o indice da primeira
        barra POSTERIOR a abertura, para nao reavaliar a barra em que se entrou.

    Retorna
    -------
    `BarrierTouch` quando houve desfecho, ou `None` quando AINDA NAO HA o que
    decidir: nenhuma barra na janela, ou nenhum toque horizontal E a barreira
    vertical ainda nao venceu.

    Toque horizontal e avaliado nas barras DISPONIVEIS, sem esperar o prazo: um stop
    tocado na barra 1 fecha na barra 1. Faltando barra para completar o horizonte, o
    que fica indeterminado e apenas o desfecho por PRAZO.
    `None` aqui significa "continua aberto", nunca "erro" -- segue o padrao do
    projeto de nao inventar default quando falta dado
    (`financial_engine.py`: sem dado => None).

    Levanta
    -------
    ValueError para lado irreconhecivel, barreira nao positiva/nao finita, ou
    barreiras invertidas (stop acima do alvo num longo, e vice-versa). Sao erros de
    DADO persistido, nao de mercado -- o fechador captura por trade e reporta, para
    uma linha corrompida nao derrubar o ciclo.

    Desempate
    ---------
    Barra que toca stop E alvo: assume o STOP (pessimista). Ver adaptacao 2 no topo
    do modulo -- a ordem intrabar nao e observavel no candle e este journal alimenta
    `outcome_learning.py`.
    """
    normalized_side = normalize_side(side)

    stop = _as_float(stop_loss_price)
    target = _as_float(take_profit_price)
    if stop is None or stop <= 0:
        raise ValueError(
            f"stop_loss_price must be a positive finite number, got {stop_loss_price!r}"
        )
    if target is None or target <= 0:
        raise ValueError(
            f"take_profit_price must be a positive finite number, got {take_profit_price!r}"
        )
    if normalized_side == "long" and stop >= target:
        raise ValueError(f"Inverted barriers for long: stop {stop} >= target {target}")
    if normalized_side == "short" and target >= stop:
        raise ValueError(f"Inverted barriers for short: target {target} >= stop {stop}")

    horizon = int(time_horizon_bars)
    if horizon <= 0:
        raise ValueError(f"time_horizon_bars must be positive, got {time_horizon_bars!r}")

    if start_index < 0:
        raise ValueError(f"start_index must be >= 0, got {start_index}")

    available = len(bars) - start_index
    if available <= 0:
        return None

    # As barras DISPONIVEIS sao avaliadas mesmo antes do prazo vencer: um stop tocado
    # na barra 1 de um horizonte de 5 tem que fechar na barra 1, nao esperar as 5.
    # O que falta de barra so importa para a barreira VERTICAL -- sem o horizonte
    # inteiro nao se pode declarar vencimento por prazo, e o trade segue aberto.
    evaluated = min(horizon, available)
    horizon_elapsed = available >= horizon

    for offset in range(evaluated):
        index = start_index + offset
        open_, high, low, _close, timestamp = _bar_fields(bars[index])

        if normalized_side == "long":
            stop_hit = low <= stop + _epsilon(stop)
            target_hit = high >= target - _epsilon(target)
        else:
            stop_hit = high >= stop - _epsilon(stop)
            target_hit = low <= target + _epsilon(target)

        if stop_hit:
            # Desempate pessimista: stop ganha do alvo quando a mesma barra toca os dois.
            return BarrierTouch(
                exit_reason=STOP_LOSS,
                exit_price=_fill_price(
                    side=normalized_side, level=stop, open_=open_, high=high, low=low
                ),
                exit_index=index,
                bars_held=offset + 1,
                gapped=bool(
                    (normalized_side == "long" and stop > high + _epsilon(stop))
                    or (normalized_side == "short" and stop < low - _epsilon(stop))
                ),
                exit_timestamp=timestamp,
            )

        if target_hit:
            return BarrierTouch(
                exit_reason=TAKE_PROFIT,
                exit_price=_fill_price(
                    side=normalized_side, level=target, open_=open_, high=high, low=low
                ),
                exit_index=index,
                bars_held=offset + 1,
                gapped=False,
                exit_timestamp=timestamp,
            )

    if not horizon_elapsed:
        return None

    # Barreira vertical: horizonte consumido sem toque horizontal. Saida a mercado
    # no fechamento da ultima barra do prazo -- mesmo ponto em que o original
    # (`events_["t1"]`) para.
    last_index = start_index + horizon - 1
    _open, _high, _low, last_close, last_timestamp = _bar_fields(bars[last_index])
    return BarrierTouch(
        exit_reason=TIME_EXIT,
        exit_price=last_close,
        exit_index=last_index,
        bars_held=horizon,
        gapped=False,
        exit_timestamp=last_timestamp,
    )
