"""Fechador de posicao paper: avalia trades abertos contra as barreiras e fecha.

O que faz
---------
Le `journal.list_open()`, reconstroi a serie de candles de cada ticker pelo
`DataHub.get_candles`, avalia o primeiro toque de stop / alvo / prazo com
`evaluate_triple_barrier` (triple_barrier.py) e chama `journal.close_trade` com o
motivo no vocabulario do journal (`paper_journal.py:118-120`).

Idempotencia
------------
`list_open()` ja filtra `exit_date is None` (`paper_journal.py:531`), entao reler a
cada ciclo basta. Como reforco -- e porque outro processo (agent_server, o scan do
Mangala) escreve o mesmo journal -- antes de fechar o fechador RELE a linha e recusa
se ela ja tiver `exit_date`. `close_trade` ja toma o lock de arquivo entre processos
(`_journal_file_lock`), mas o guard evita a corrida de leitura: sem ele, dois
processos decidem fechar o mesmo trade e o segundo sobrescreve o PnL do primeiro.

Mercado fechado
---------------
Nao e erro. O fechador usa o ULTIMO candle disponivel e nao reavalia o que ja foi
fechado. Faltando candle posterior a entrada, o trade e simplesmente "ainda nao
avaliavel" -- nao ha tentativa de inventar preco.

Dry-run
-------
`dry_run` e o DEFAULT desta funcao, de proposito: o primeiro ciclo em producao deve
ser simulacao. Em dry-run o fechador loga exatamente o que fecharia, com preco e
motivo, e nao escreve no journal. Para armar o fechamento real, o operador precisa
desligar explicitamente (env `SUPEREZIO_POSITION_CLOSER_DRY_RUN=0`, ver
`dry_run_from_env`).

Split
-----
Detectado e NAO aplicado: quando uma barra da janela abre num multiplo conhecido de
split em relacao ao fechamento anterior (`detect_split_factor`), o trade e PULADO com
o motivo `suspected_split` em vez de ser fechado. O ajuste automatico das barreiras
ficou de fora (ver relatorio): ajustar exige saber que houve split de verdade, e a
deteccao por preco nao distingue um split 2:1 de uma queda real de 50% -- as duas
invalidam as barreiras persistidas, e fechar em cima de barreira invalida inventaria
um PnL. A linha fica aberta e o operador decide.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.trading.holding_period import holding_period_bars
from core.trading.paper_journal import PaperJournal, _parse_utc_datetime
from core.trading.triple_barrier import (
    BARRIER_EXIT_REASONS,
    evaluate_triple_barrier,
)

logger = logging.getLogger(__name__)

# Fatores de split/grupamento usuais. A comparacao e por PROPORCAO entre o
# fechamento anterior e o open da barra seguinte, com tolerancia apertada (1%):
# uma queda real de 50% existe, mas e rara, e e exatamente o caso ambiguo em que
# fechar em cima da barreira antiga inventaria resultado.
_KNOWN_SPLIT_RATIOS: tuple[float, ...] = (2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 15.0, 20.0)
_SPLIT_TOLERANCE = 0.01

# Motivos de PULO (nao sao `exit_reason`: nada foi fechado).
SKIP_MISSING_BARRIERS = "missing_barriers"
SKIP_INVALID_BARRIERS = "invalid_barriers"
SKIP_ENTRY_UNPARSABLE = "entry_date_unparsable"
SKIP_NO_MARKET_DATA = "no_market_data"
SKIP_NO_BAR_AFTER_ENTRY = "no_bar_after_entry"
SKIP_HORIZON_PENDING = "horizon_not_elapsed"
SKIP_SUSPECTED_SPLIT = "suspected_split"
SKIP_ALREADY_CLOSED = "already_closed"
SKIP_JOURNAL_ERROR = "journal_error"

STATUS_CLOSED = "closed"
STATUS_WOULD_CLOSE = "would_close"
STATUS_SKIPPED = "skipped"


@dataclass(frozen=True)
class CloseDecision:
    """Veredito do fechador para UM trade aberto."""

    trade_id: str
    ticker: str
    status: str  # "closed" | "would_close" | "skipped"
    reason: str
    exit_reason: str | None = None
    exit_price: float | None = None
    exit_timestamp: str | None = None
    bars_held: int | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "status": self.status,
            "reason": self.reason,
            "exit_reason": self.exit_reason,
            "exit_price": self.exit_price,
            "exit_timestamp": self.exit_timestamp,
            "bars_held": self.bars_held,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CloserReport:
    """Resultado de um ciclo do fechador."""

    dry_run: bool
    evaluated: int
    decisions: list[CloseDecision] = field(default_factory=list)
    throttle_skipped: bool = False

    def _count(self, status: str) -> int:
        return sum(1 for d in self.decisions if d.status == status)

    @property
    def closed(self) -> int:
        return self._count(STATUS_CLOSED)

    @property
    def would_close(self) -> int:
        return self._count(STATUS_WOULD_CLOSE)

    @property
    def skipped(self) -> int:
        return self._count(STATUS_SKIPPED)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "evaluated": self.evaluated,
            "closed": self.closed,
            "would_close": self.would_close,
            "skipped": self.skipped,
            "throttle_skipped": self.throttle_skipped,
            "decisions": [d.to_dict() for d in self.decisions],
        }


def dry_run_from_env() -> bool:
    """Liga/desliga a simulacao. DEFAULT SIMULACAO (nao fecha nada).

    O fechamento real so acontece com `SUPEREZIO_POSITION_CLOSER_DRY_RUN` contendo
    explicitamente "0"/"false"/"no". Qualquer outro valor (inclusive ausente) mantem
    a simulacao, porque um ciclo que fecha posicao com dinheiro em jogo nao pode ser
    ligado por omissao de configuracao.
    """
    token = str(os.getenv("SUPEREZIO_POSITION_CLOSER_DRY_RUN", "1")).strip().lower()
    return token not in {"0", "false", "no", "off"}


def _extract_barriers(row: Mapping[str, Any]) -> tuple[float, float, int] | None:
    """Le as barreiras persistidas na abertura da linha do journal.

    `time_horizon_bars` pode faltar em linha antiga: nesse caso o horizonte e
    reconstruido a partir de `expected_holding_period` pelo mapa de produto
    (holding_period.py). Stop e alvo, nao: sem eles nao ha barreira horizontal para
    avaliar, e chutar um default fecharia o trade por um preco inventado.
    """
    stop = _as_float(row.get("stop_loss_price"))
    target = _as_float(row.get("take_profit_price"))
    if stop is None or target is None or stop <= 0 or target <= 0:
        return None
    horizon = _as_float(row.get("time_horizon_bars"))
    if horizon is None or horizon <= 0:
        horizon = float(holding_period_bars(row.get("expected_holding_period")))
    return stop, target, int(horizon)


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def detect_split_factor(
    bars: Sequence[Mapping[str, Any]],
    *,
    start_index: int = 0,
    tolerance: float = _SPLIT_TOLERANCE,
) -> float | None:
    """Fator de split quando uma barra abre num multiplo conhecido do fechamento anterior.

    Positivo = split (preco dividido), negativo = grupamento (preco multiplicado).
    Inclui a barra ANTERIOR a `start_index` na varredura: um split ocorrido entre a
    barra de entrada e a primeira barra avaliada aparece exatamente nesse degrau.
    """
    begin = max(start_index - 1, 0)
    for index in range(begin, len(bars) - 1):
        prev_close = _as_float(bars[index].get("close"))
        next_open = _as_float(bars[index + 1].get("open"))
        if prev_close is None or next_open is None or prev_close <= 0 or next_open <= 0:
            continue
        forward = prev_close / next_open
        reverse = next_open / prev_close
        for ratio in _KNOWN_SPLIT_RATIOS:
            if abs(forward - ratio) <= tolerance * ratio:
                return ratio
            if abs(reverse - ratio) <= tolerance * ratio:
                return -ratio
    return None


def _find_start_index(bars: Sequence[Mapping[str, Any]], entry_date: Any) -> int | None:
    """Indice da primeira barra POSTERIOR a entrada.

    A barra de entrada nao e reavaliada: o trade entrou dentro dela, entao um toque
    ali nao e um desfecho do trade (nao se sabe se o toque veio antes ou depois da
    entrada).
    """
    entry = _parse_utc_datetime(entry_date)
    if entry is None:
        return None
    for index, bar in enumerate(bars):
        stamp = _parse_utc_datetime(bar.get("datetime") or bar.get("observed_at"))
        if stamp is not None and stamp > entry:
            return index
    return None


def _candles_from(data_hub: Any, ticker: str, timeframe: str) -> list[Mapping[str, Any]]:
    """Candles do DataHub, ou lista vazia quando o provider devolve erro."""
    result = data_hub.get_candles(ticker, timeframe)
    if not isinstance(result, Mapping):
        return []
    if result.get("error"):
        logger.debug(
            "Position closer: candle fetch error ticker=%s err=%s", ticker, result["error"]
        )
        return []
    candles = result.get("candles")
    return candles if isinstance(candles, list) else []


def _evaluate_one(
    row: Mapping[str, Any],
    *,
    data_hub: Any,
    timeframe: str,
) -> CloseDecision:
    """Veredito (sem escrever nada) para um trade aberto."""
    trade_id = str(row.get("trade_id") or "")
    ticker = str(row.get("ticker") or "").strip().upper()
    barriers = _extract_barriers(row)
    if barriers is None:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_MISSING_BARRIERS,
            detail="linha sem stop_loss_price/take_profit_price persistidos na abertura",
        )
    stop, target, horizon = barriers

    entry_date = row.get("entry_date")
    if _parse_utc_datetime(entry_date) is None:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_ENTRY_UNPARSABLE,
            detail=f"entry_date invalida: {entry_date!r}",
        )

    bars = _candles_from(data_hub, ticker, timeframe)
    if not bars:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_NO_MARKET_DATA,
            detail=f"sem candles para {ticker} ({timeframe})",
        )

    start_index = _find_start_index(bars, entry_date)
    if start_index is None:
        # Mercado fechado / candle ainda nao publicado: nao e erro, nao ha o que avaliar.
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_NO_BAR_AFTER_ENTRY,
            detail="nenhuma barra posterior a entrada ainda",
        )

    split = detect_split_factor(bars, start_index=start_index)
    if split is not None:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_SUSPECTED_SPLIT,
            detail=(
                f"degrau de preco compativel com {'split' if split > 0 else 'grupamento'} "
                f"{abs(split):g}:1 -- barreiras persistidas podem estar em escala antiga"
            ),
        )

    try:
        touch = evaluate_triple_barrier(
            bars,
            side=row.get("direction"),
            stop_loss_price=stop,
            take_profit_price=target,
            time_horizon_bars=horizon,
            start_index=start_index,
        )
    except ValueError as exc:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_INVALID_BARRIERS,
            detail=str(exc),
        )

    if touch is None:
        return CloseDecision(
            trade_id=trade_id,
            ticker=ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_HORIZON_PENDING,
            detail=f"horizonte de {horizon} barras ainda nao venceu",
        )

    return CloseDecision(
        trade_id=trade_id,
        ticker=ticker,
        status=STATUS_WOULD_CLOSE,
        reason=touch.exit_reason,
        exit_reason=touch.exit_reason,
        exit_price=round(touch.exit_price, 6),
        exit_timestamp=touch.exit_timestamp,
        bars_held=touch.bars_held,
        detail=f"stop={stop} target={target} horizonte={horizon} gap={touch.gapped}",
    )


def close_positions(
    journal: PaperJournal | None = None,
    *,
    data_hub: Any = None,
    dry_run: bool = True,
    timeframe: str = "6M",
) -> CloserReport:
    """Um ciclo do fechador: avalia os trades abertos e fecha os que bateram barreira.

    `dry_run=True` (default) nao escreve nada: devolve o mesmo veredito com
    `status="would_close"` para o operador conferir antes de armar o fechamento real.
    """
    journal = journal or PaperJournal()
    if data_hub is None:
        from data.data_hub import (
            hub as data_hub,
        )

    open_trades = journal.list_open()
    decisions: list[CloseDecision] = []

    for row in open_trades:
        try:
            decision = _evaluate_one(row, data_hub=data_hub, timeframe=timeframe)
        except Exception as exc:
            logger.exception("Position closer failed to evaluate trade")
            decisions.append(
                CloseDecision(
                    trade_id=str(row.get("trade_id") or ""),
                    ticker=str(row.get("ticker") or ""),
                    status=STATUS_SKIPPED,
                    reason=SKIP_JOURNAL_ERROR,
                    detail=str(exc)[:200],
                )
            )
            continue

        if decision.status == STATUS_WOULD_CLOSE and not dry_run:
            decision = _apply_close(journal, decision)
        decisions.append(decision)

    report = CloserReport(dry_run=dry_run, evaluated=len(open_trades), decisions=decisions)
    logger.info(
        "position_closer_cycle dry_run=%s evaluated=%d closed=%d would_close=%d skipped=%d",
        dry_run,
        report.evaluated,
        report.closed,
        report.would_close,
        report.skipped,
    )
    return report


def _apply_close(journal: PaperJournal, decision: CloseDecision) -> CloseDecision:
    """Fecha de verdade, revalidando a linha antes (idempotencia entre processos)."""
    if decision.exit_reason not in BARRIER_EXIT_REASONS:  # pragma: no cover - guarda de contrato
        return CloseDecision(
            trade_id=decision.trade_id,
            ticker=decision.ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_JOURNAL_ERROR,
            detail=f"motivo fora do vocabulario do journal: {decision.exit_reason!r}",
        )

    current = journal.get_trade(decision.trade_id)
    if current is None:
        return CloseDecision(
            trade_id=decision.trade_id,
            ticker=decision.ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_JOURNAL_ERROR,
            detail="trade desapareceu do journal entre a leitura e o fechamento",
        )
    if current.get("exit_date") is not None:
        return CloseDecision(
            trade_id=decision.trade_id,
            ticker=decision.ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_ALREADY_CLOSED,
            detail=f"ja fechado em {current.get('exit_date')} por {current.get('exit_reason')}",
        )

    closed = journal.close_trade(
        decision.trade_id,
        exit_price=float(decision.exit_price or 0.0),
        exit_reason=str(decision.exit_reason),
        exit_date=decision.exit_timestamp,
    )
    if closed is None:
        return CloseDecision(
            trade_id=decision.trade_id,
            ticker=decision.ticker,
            status=STATUS_SKIPPED,
            reason=SKIP_JOURNAL_ERROR,
            detail="close_trade nao encontrou o trade",
        )

    logger.info(
        "position_closer_closed trade_id=%s ticker=%s reason=%s exit=%.4f bars=%s outcome=%s pnl=%.2f",
        decision.trade_id,
        decision.ticker,
        decision.exit_reason,
        float(decision.exit_price or 0.0),
        decision.bars_held,
        closed.outcome,
        closed.pnl_amount or 0.0,
    )
    return CloseDecision(
        trade_id=decision.trade_id,
        ticker=decision.ticker,
        status=STATUS_CLOSED,
        reason=decision.reason,
        exit_reason=decision.exit_reason,
        exit_price=decision.exit_price,
        exit_timestamp=decision.exit_timestamp,
        bars_held=decision.bars_held,
        detail=decision.detail,
    )
