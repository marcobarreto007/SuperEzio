"""Caderneta de recomendacoes - o corpus que substitui o paper order desligado.

O PROBLEMA QUE ISTO RESOLVE
---------------------------
O paper order esta desligado e nao volta:

    SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT = "0"   (intents.py:217)
    is_execution_frozen() -> True               (f51_trade_gate.py:62)

E mesmo ligado ele seria ficcao: NAO EXISTE API DO TD. O dono opera a mao no
TD Direct Investing. O sistema nao e executor -- e EMISSOR DE RECOMENDACAO PARA
HUMANO. Simular uma submissao que nunca acontece produz um journal cheio de
trades que ninguem fez: medido em 14/09/2026, `data/paper_journal.jsonl` tem 534
linhas, ZERO com `expert_predictions`, ZERO com `stop_loss_price`, DUAS com
`outcome`. Dai `adaptive_outcomes.sqlite3` estar em `processed_outcomes 0` e
`expert_stats 0`: o motor de aprendizado esta correto e alimentado com nada.

O que precisa existir e o registro DO QUE O SISTEMA RECOMENDOU. Cada linha desta
caderneta e uma recomendacao, e o dono -- o atuador -- marca se executou e a que
preco. O aprendizado come dai.

DUAS COISAS DIFERENTES, E O APRENDIZADO PRECISA DISTINGUIR
----------------------------------------------------------
`outcome_source` diz de onde veio o desfecho, e nao e detalhe cosmetico:

  - "executed"       -> preco que o DONO digitou. E a realidade: houve dinheiro.
  - "counterfactual" -> o que o mercado fez, rotulado pelo `triple_barrier` sobre
                        o preco que a recomendacao PEDIU. Nao houve dinheiro.

O desfecho real SEMPRE ganha do contrafactual: quando o dono reporta a execucao,
`record_executed_outcome` promove o desfecho real e guarda o contrafactual
anterior em `counterfactual` (para comparar "o que eu fiz" com "o que teria
acontecido"). O inverso nunca acontece -- `label_counterfactuals` pula toda linha
que ja tem desfecho real, porque sobrescrever realidade com simulacao e
exatamente o defeito que esta caderneta veio corrigir.

`learning_rows()` devolve, por DEFAULT, apenas desfechos reais. Quem quiser
aprendizado-sombra (o que a recomendacao teria rendido se executada) pede
explicitamente `include_counterfactual=True` e recebe `outcome_source` em cada
linha para poder separar.

FORMATO E PERSISTENCIA
----------------------
JSONL append-only, no padrao do `paper_journal` -- mesmas garantias, nenhuma
invencao:

  - a linha e o MESMO vocabulario do journal (`ticker`, `direction`,
    `entry_price`, `shares`, `stop_loss_price`, `take_profit_price`,
    `time_horizon_bars`, `entry_date`...). Isso NAO e estetica: e o que permite ao
    fechador avaliar uma recomendacao com `position_closer.evaluate_row` e aos
    motores consumirem a linha com `OutcomeLearningEngine.process_trade`, sem
    nenhum tradutor no meio.
  - travas: RLock de thread + `_journal_file_lock` (lock de arquivo entre
    processos) REAPROVEITADO de `paper_journal`; escrita de update atomica
    (tmp + fsync + os.replace); quarentena de linha corrompida; recusa de truncar
    a caderneta de producao; recusa de escrever no arquivo do operador sob pytest.
  - `recommendation_id` e DETERMINISTICO a partir do conteudo da recomendacao.
    Re-gravar a mesma emissao (retry, chamada repetida) devolve o id existente e
    nao escreve segunda linha -- idempotencia sem tabela de dedup.

O QUE ESTA CADERNETA NAO FAZ
----------------------------
Nao fecha posicao, nao submete ordem, nao apaga nem migra o `paper_journal`
(o fechador e o `close_trade` do `auto_execute_paper` dependem dele). Ela nasce AO
LADO. A migracao do paper order e decisao posterior do dono.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import math
import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# `_journal_file_lock` e privado do paper_journal, mas e exatamente a trava que
# esta caderneta precisa (lock de arquivo entre processos, Windows-safe) e o
# pedido e literal: reaproveitar, nao reimplementar. `_parse_utc_datetime` vem
# pelo mesmo motivo do position_closer.py:57 -- e a unica definicao que aceita o
# formato exato gravado (Z e offset).
from core.trading.paper_journal import (
    _journal_file_lock,
    _parse_utc_datetime,
)

logger = logging.getLogger(__name__)

DEFAULT_LEDGER_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "recommendation_ledger.jsonl"
)

# Vocabulario do desfecho -- identico ao de `paper_journal.PaperTrade.outcome`.
OUTCOME_WIN = "win"
OUTCOME_LOSS = "loss"
OUTCOME_BREAKEVEN = "breakeven"
TERMINAL_OUTCOMES: frozenset[str] = frozenset({OUTCOME_WIN, OUTCOME_LOSS, OUTCOME_BREAKEVEN})

# PROVENIENCIA DO DESFECHO -- o campo que o aprendizado precisa distinguir.
OUTCOME_SOURCE_EXECUTED = "executed"
OUTCOME_SOURCE_COUNTERFACTUAL = "counterfactual"
OUTCOME_SOURCES: frozenset[str] = frozenset(
    {OUTCOME_SOURCE_EXECUTED, OUTCOME_SOURCE_COUNTERFACTUAL}
)

DIRECTION_LONG = "long"
DIRECTION_SHORT = "short"

# Mesmo limiar de `paper_journal.PaperTrade.close_trade` (linhas 158-164): abaixo
# de um centavo nao houve ganho nem perda, houve empate. Copiado de la de
# proposito, e ha teste amarrando os dois (`test_ledger_pnl_bate_com_o_do_journal`)
# para que uma mudanca num lado sem o outro quebre a suite.
_BREAKEVEN_TOLERANCE = 0.01

# Mesma regra de inversao de `triple_barrier.evaluate_triple_barrier`: stop acima
# do alvo num longo (e vice-versa num curto) e erro de DADO, nao de mercado.
_LONG_SIDES = frozenset({"LONG", "BUY", "BULLISH"})
_SHORT_SIDES = frozenset({"SHORT", "SELL", "BEARISH"})


class LedgerError(RuntimeError):
    """Erro de uso da caderneta (dado invalido, transicao proibida)."""


# ──────────────────────────────────────────────────────────────────────────────
# Modelo
# ──────────────────────────────────────────────────────────────────────────────


def normalize_direction(value: object) -> str:
    """Normaliza o lado para "long" | "short" (mesmas siglas do triple_barrier)."""
    token = str(value or "").strip().upper()
    if token in _LONG_SIDES:
        return DIRECTION_LONG
    if token in _SHORT_SIDES:
        return DIRECTION_SHORT
    raise ValueError(f"Direcao irreconhecivel na recomendacao: {value!r}")


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _iso_utc(value: Any) -> str | None:
    """ISO-8601 UTC. Aceita datetime e string; recusa string que nao parseia."""
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat()
    parsed = _parse_utc_datetime(value)
    return parsed.isoformat() if parsed is not None else None


def _outcome_from_pnl(pnl_amount: float) -> str:
    """Regra de desfecho do journal, isolada para poder ser testada contra ele."""
    if pnl_amount > _BREAKEVEN_TOLERANCE:
        return OUTCOME_WIN
    if pnl_amount < -_BREAKEVEN_TOLERANCE:
        return OUTCOME_LOSS
    return OUTCOME_BREAKEVEN


def compute_pnl(
    *, direction: str, entry_price: float, exit_price: float, shares: float
) -> tuple[float, float]:
    """(pnl_amount, pnl_percent) -- mesma aritmetica de `PaperTrade.close_trade`."""
    if direction == DIRECTION_LONG:
        pnl_amount = (exit_price - entry_price) * shares
    else:
        pnl_amount = (entry_price - exit_price) * shares
    notional = entry_price * shares
    pnl_percent = (pnl_amount / notional) * 100 if notional > 0 else 0.0
    return pnl_amount, pnl_percent


@dataclass
class Recommendation:
    """Uma recomendacao emitida pelo sistema, antes de qualquer execucao.

    Os nomes dos campos de mercado sao os do `paper_journal` de proposito (ver o
    docstring do modulo): e o que torna a linha consumivel pelo fechador e pelos
    motores sem tradutor.
    """

    ticker: str
    direction: str
    entry_price: float
    shares: float
    expert_source: str = ""
    rationale: str = ""
    created_at: str | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    time_horizon_bars: int | None = None
    expected_holding_period: str = "unknown"
    thesis: str = ""
    verdict_at_entry: str = ""
    risk_assessment: str = ""
    # Contexto de aprendizado, no mesmo formato que `_extract_learning_context`
    # (auto_execute_paper.py:963) ja produz. NAO e preenchido por padrao: prever
    # `expert_predictions` aqui seria fabricar justamente o sinal que os motores
    # aprendem -- quem sabe a predicao e o emissor da recomendacao.
    expert_predictions: dict[str, dict[str, Any]] = field(default_factory=dict)
    expert_attribution: dict[str, float] = field(default_factory=dict)
    confidence_at_entry: float | None = None
    prediction_probability_at_entry: float | None = None
    prediction_class_at_entry: str | None = None
    calibration_status: str = "unknown"
    model_id: str = ""
    forecast_as_of: str = ""
    forecast_horizon: str | int | None = None
    risk_at_entry: float | None = None
    fees: float = 0.0
    slippage: float = 0.0
    tags: list[str] = field(default_factory=list)
    run_id: str = ""
    """Id da emissao. Dois ciclos do pipeline que recomendam o MESMO ativo no
    MESMO preco em instantes diferentes sao duas recomendacoes, nao uma."""

    def __post_init__(self) -> None:
        self.ticker = str(self.ticker or "").strip().upper()
        if not self.ticker:
            raise ValueError("Recomendacao sem ticker")
        self.direction = normalize_direction(self.direction)

        self.entry_price = _as_float(self.entry_price) or 0.0
        if self.entry_price <= 0:
            raise ValueError(f"Recomendacao sem preco de entrada utilizavel: {self.entry_price!r}")
        self.shares = _as_float(self.shares) or 0.0
        if self.shares <= 0:
            raise ValueError(f"Recomendacao sem tamanho utilizavel: {self.shares!r}")

        self.stop_loss_price = _as_float(self.stop_loss_price)
        self.take_profit_price = _as_float(self.take_profit_price)
        if self.stop_loss_price is not None and self.stop_loss_price <= 0:
            raise ValueError(f"Stop nao positivo: {self.stop_loss_price!r}")
        if self.take_profit_price is not None and self.take_profit_price <= 0:
            raise ValueError(f"Alvo nao positivo: {self.take_profit_price!r}")
        self._assert_barriers_not_inverted()

        if self.time_horizon_bars is not None:
            horizon = int(self.time_horizon_bars)
            if horizon <= 0:
                raise ValueError(f"Prazo em barras nao positivo: {self.time_horizon_bars!r}")
            self.time_horizon_bars = horizon

        self.created_at = _iso_utc(self.created_at) or datetime.now(UTC).isoformat()

    def _assert_barriers_not_inverted(self) -> None:
        stop, target = self.stop_loss_price, self.take_profit_price
        if stop is None or target is None:
            return
        if self.direction == DIRECTION_LONG and stop >= target:
            raise ValueError(f"Barreiras invertidas num longo: stop {stop} >= alvo {target}")
        if self.direction == DIRECTION_SHORT and target >= stop:
            raise ValueError(f"Barreiras invertidas num curto: alvo {target} >= stop {stop}")

    @property
    def barriers(self) -> dict[str, Any]:
        """Quais barreiras a recomendacao NASCEU com (o "por que" de um pulo).

        O fechador pula linha sem stop/alvo (`SKIP_MISSING_BARRIERS`) e sem prazo
        ele reconstroi pelo `expected_holding_period`. Sem esta declaracao, uma
        recomendacao que nunca e rotulada vira silencio; com ela, o motivo esta na
        propria linha.
        """
        return {
            "stop": self.stop_loss_price is not None,
            "target": self.take_profit_price is not None,
            "horizon": self.time_horizon_bars is not None,
        }

    @property
    def is_actionable(self) -> bool:
        """Stop E alvo presentes -- o que a barreira tripla precisa para rotular."""
        return self.stop_loss_price is not None and self.take_profit_price is not None

    def recommendation_id(self) -> str:
        """Id deterministico do CONTEUDO (ver `build_recommendation_id`)."""
        return build_recommendation_id(
            ticker=self.ticker,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss_price=self.stop_loss_price,
            take_profit_price=self.take_profit_price,
            time_horizon_bars=self.time_horizon_bars,
            expert_source=self.expert_source,
            created_at=self.created_at,
        )

    def to_dict(self) -> dict[str, Any]:
        """A linha da caderneta. Vocabulario identico ao do paper_journal."""
        return {
            "recommendation_id": self.recommendation_id(),
            # ── identidade da recomendacao ────────────────────────────────────
            "ticker": self.ticker,
            "symbol": self.ticker,
            "direction": self.direction,
            "created_at": self.created_at,
            "entry_date": self.created_at,
            "rationale": self.rationale,
            "expert_source": self.expert_source,
            "run_id": self.run_id,
            "barriers": self.barriers,
            # ── niveis pedidos ────────────────────────────────────────────────
            "entry_price": self.entry_price,
            "shares": self.shares,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "time_horizon_bars": self.time_horizon_bars,
            "expected_holding_period": self.expected_holding_period,
            # ── tese (vocabulario do journal) ─────────────────────────────────
            "thesis": self.thesis,
            "verdict_at_entry": self.verdict_at_entry,
            "risk_assessment": self.risk_assessment,
            "expert_predictions": dict(self.expert_predictions),
            "expert_attribution": dict(self.expert_attribution),
            "confidence_at_entry": self.confidence_at_entry,
            "prediction_probability_at_entry": self.prediction_probability_at_entry,
            "prediction_class_at_entry": self.prediction_class_at_entry,
            "calibration_status": self.calibration_status,
            "model_id": self.model_id,
            "forecast_as_of": self.forecast_as_of,
            "forecast_horizon": self.forecast_horizon,
            "risk_at_entry": self.risk_at_entry,
            "fees": self.fees,
            "slippage": self.slippage,
            "tags": list(self.tags),
            # ── execucao: o dono e o atuador. None = DESCONHECIDO. ────────────
            "executed": None,
            "executed_at": None,
            "executed_price": None,
            "execution_note": "",
            "execution_reported_at": None,
            # ── desfecho (preenchido depois) ──────────────────────────────────
            "outcome": None,
            "outcome_source": None,
            "outcome_at": None,
            "exit_price": None,
            "exit_date": None,
            "exit_reason": None,
            "bars_held": None,
            "pnl_amount": None,
            "pnl_percent": None,
            "counterfactual": None,
            "last_label_reason": None,
            "last_labeled_at": None,
            "updated_at": self.created_at,
        }


def build_recommendation_id(
    *,
    ticker: str,
    direction: str,
    entry_price: float,
    stop_loss_price: float | None,
    take_profit_price: float | None,
    time_horizon_bars: int | None,
    expert_source: str,
    created_at: str,
) -> str:
    """`rec-<sha256[:16]>` do conteudo da recomendacao.

    `created_at` entra na conta de proposito: duas recomendacoes iguais emitidas
    em instantes diferentes sao DUAS recomendacoes (o sistema recomendou duas
    vezes), e colapsa-las apagaria a insistencia do emissor -- que e sinal. O que
    colapsa e a mesma emissao gravada duas vezes, e para isso basta o id ser
    funcao pura do conteudo: retry virou no-op.
    """
    payload = "|".join(
        [
            str(ticker).strip().upper(),
            str(direction).strip().lower(),
            f"{float(entry_price):.6f}",
            "" if stop_loss_price is None else f"{float(stop_loss_price):.6f}",
            "" if take_profit_price is None else f"{float(take_profit_price):.6f}",
            "" if time_horizon_bars is None else str(int(time_horizon_bars)),
            str(expert_source or "").strip().lower(),
            str(created_at),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"rec-{digest[:16]}"


@dataclass(frozen=True)
class RecordResult:
    """O que aconteceu com a gravacao -- `created=False` significa idempotencia."""

    recommendation_id: str
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return {"recommendation_id": self.recommendation_id, "created": self.created}


@dataclass(frozen=True)
class LabelReport:
    """Resultado de um ciclo do rotulador contrafactual."""

    dry_run: bool
    evaluated: int = 0
    labeled: int = 0
    pending: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "evaluated": self.evaluated,
            "labeled": self.labeled,
            "pending": self.pending,
            "skipped_reasons": dict(self.skipped_reasons),
            "decisions": list(self.decisions),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Caderneta
# ──────────────────────────────────────────────────────────────────────────────

# Guarda de producao: a caderneta do operador nunca pode ser truncada em silencio.
_PRODUCTION_LEDGER = DEFAULT_LEDGER_PATH.resolve()


class RecommendationLedger:
    """Caderneta append-only de recomendacoes. JSONL, uma linha por recomendacao."""

    def __init__(self, path: Path | None = None):
        configured = str(os.getenv("SUPEREZIO_RECOMMENDATION_LEDGER_PATH") or "").strip()
        self._path = path or (Path(configured) if configured else DEFAULT_LEDGER_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_environment = (
            "operator" if self._path.resolve() == _PRODUCTION_LEDGER else "isolated"
        )
        # Reentrante: os read-modify-write abaixo seguram o lock e chamam
        # _read_all/_rewrite dentro dele (mesmo padrao de PaperJournal._lock).
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def storage_environment(self) -> str:
        return self._storage_environment

    # ── persistencia (espelha paper_journal) ──────────────────────────────────

    def _assert_write_allowed(self) -> None:
        """Pytest nunca pode mutar a caderneta do operador."""
        if self._path.resolve() == _PRODUCTION_LEDGER and os.getenv("PYTEST_CURRENT_TEST"):
            raise LedgerError(
                "Testes nao podem escrever na caderneta do operador; injete um caminho temporario"
            )

    def _prepare_new_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(entry)
        claimed = str(prepared.get("storage_environment") or self._storage_environment).strip()
        if claimed != self._storage_environment:
            raise LedgerError(
                f"Ambiente da caderneta divergente: linha={claimed} storage={self._storage_environment}"
            )
        prepared["storage_environment"] = self._storage_environment
        prepared["provenance"] = str(prepared.get("provenance") or "recommendation_ledger").strip()
        if not prepared["provenance"]:
            raise LedgerError("Proveniencia da caderneta e obrigatoria")
        return prepared

    def _quarantine_raw_line(self, raw_line: str) -> None:
        """Preserva linha corrompida antes que um _rewrite a apague (igual ao journal)."""
        try:
            quarantine_path = self._path.with_name(self._path.name + ".quarantine")
            with open(quarantine_path, "a", encoding="utf-8") as f:
                f.write(raw_line.rstrip("\n") + "\n")
        except OSError:
            logger.exception("Nao foi possivel quarentenar linha corrompida da caderneta")

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock, open(self._path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    self._quarantine_raw_line(raw_line)
                    logger.warning("Linha corrompida quarentenada na caderneta")
        return entries

    def _append(self, entry: dict[str, Any]) -> None:
        self._assert_write_allowed()
        prepared = self._prepare_new_entry(entry)
        with self._lock, open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(prepared, ensure_ascii=False) + "\n")

    def _rewrite(self, entries: Sequence[dict[str, Any]]) -> None:
        """Reescreve a caderneta inteira (usado para updates), de forma atomica."""
        resolved = self._path.resolve()
        if resolved == _PRODUCTION_LEDGER and len(entries) == 0:
            raise LedgerError(
                f"Recusando truncar a caderneta de producao em {resolved}. "
                f"Para zerar, apague o arquivo a mao e com intencao explicita."
            )
        self._assert_write_allowed()
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        with self._lock:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)

    # ── escrita ───────────────────────────────────────────────────────────────

    def record(
        self,
        recommendation: Recommendation | Mapping[str, Any],
        *,
        dedupe_key: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> RecordResult:
        """Grava a recomendacao. Idempotente: re-gravar a mesma emissao e no-op.

        `dedupe_key` sobrepoe o id deterministico -- e por onde o pipeline amarra a
        gravacao ao `run_id` (mesma ideia de `bob-{run_id[:12]}` no journal).
        """
        row = (
            recommendation.to_dict()
            if isinstance(recommendation, Recommendation)
            else dict(recommendation)
        )
        self._assert_minimum_row(row)
        recommendation_id = str(dedupe_key or row.get("recommendation_id") or "").strip()
        if not recommendation_id:
            raise LedgerError("Linha sem recommendation_id e sem dedupe_key")
        row["recommendation_id"] = recommendation_id
        row["trade_id"] = recommendation_id
        if extra:
            row.update(dict(extra))
        row["barriers"] = dict(row.get("barriers") or {})

        # A guarda vem ANTES do lock: `_journal_file_lock` cria o arquivo `.lock`
        # como efeito colateral, e um teste que so quer provar a recusa nao pode
        # deixar lixo no diretorio do operador.
        self._assert_write_allowed()

        with self._lock, _journal_file_lock(self._path):
            entries = self._read_all()
            for entry in entries:
                if entry.get("recommendation_id") == recommendation_id:
                    return RecordResult(recommendation_id=recommendation_id, created=False)
            self._append(row)
        logger.info(
            "recommendation_recorded id=%s %s %s @ %s",
            recommendation_id,
            row.get("ticker"),
            row.get("direction"),
            row.get("entry_price"),
        )
        return RecordResult(recommendation_id=recommendation_id, created=True)

    def _assert_minimum_row(self, row: Mapping[str, Any]) -> None:
        """O minimo para a linha ser util depois: ativo, lado, entrada e tamanho."""
        if not str(row.get("ticker") or row.get("symbol") or "").strip():
            raise LedgerError("Linha da caderneta sem ticker")
        if not str(row.get("direction") or row.get("side") or "").strip():
            raise LedgerError("Linha da caderneta sem direcao")
        entry = _as_float(row.get("entry_price"))
        if entry is None or entry <= 0:
            raise LedgerError("Linha da caderneta sem preco de entrada utilizavel")
        shares = _as_float(row.get("shares") or row.get("qty"))
        if shares is None or shares <= 0:
            raise LedgerError("Linha da caderneta sem tamanho utilizavel")

    def _mutate(
        self,
        recommendation_id: str,
        mutate: Any,
        *,
        skip_if: Any = None,
    ) -> dict[str, Any] | None:
        """Read-modify-write com lock de arquivo. `skip_if(row)` evita rewrite inutil."""
        # Mesmo motivo de `record`: a guarda precede o lock, que cria o `.lock`.
        self._assert_write_allowed()
        with self._lock, _journal_file_lock(self._path):
            entries = self._read_all()
            for index, entry in enumerate(entries):
                if entry.get("recommendation_id") != recommendation_id:
                    continue
                if skip_if is not None and skip_if(entry):
                    return entry
                updated = dict(entry)
                mutate(updated)
                updated["updated_at"] = datetime.now(UTC).isoformat()
                entries[index] = updated
                self._rewrite(entries)
                return updated
        logger.warning("Recomendacao nao encontrada na caderneta: %s", recommendation_id)
        return None

    def mark_execution(
        self,
        recommendation_id: str,
        *,
        executed: bool | None,
        executed_at: str | None = None,
        executed_price: float | None = None,
        note: str = "",
    ) -> dict[str, Any] | None:
        """O dono marca "executei / nao executei". Ele e o atuador.

        `executed=None` volta a linha para DESCONHECIDO. Marcar `False` limpa o
        preco executado (nao existe preco de uma execucao que nao houve). A
        marcacao e reescrevivel -- o dono pode corrigir um engano -- e `skip_if`
        garante que remarcar o mesmo valor nao gera rewrite nem linha nova.

        `executed_at` nao informado significa "quando o dono reportou", e nao
        "agora": remarcar a mesma execucao PRESERVA o instante ja gravado em vez de
        carimbar um novo a cada chamada. Sem isso a marcacao nunca seria idempotente
        e o instante da execucao andaria sozinho para frente.
        """
        explicit_moment = _iso_utc(executed_at)
        price = _as_float(executed_price)

        def _apply(row: dict[str, Any]) -> None:
            if explicit_moment is not None:
                moment = explicit_moment
            elif executed is True:
                moment = row.get("executed_at") or datetime.now(UTC).isoformat()
            else:
                moment = None
            row["executed"] = executed
            row["executed_at"] = moment
            row["executed_price"] = price if executed is True else None
            row["execution_note"] = str(note or "")
            row["execution_reported_at"] = datetime.now(UTC).isoformat()

        def _unchanged(row: Mapping[str, Any]) -> bool:
            return (
                row.get("executed") == executed
                and (explicit_moment is None or row.get("executed_at") == explicit_moment)
                and _as_float(row.get("executed_price")) == (price if executed is True else None)
                and str(row.get("execution_note") or "") == str(note or "")
            )

        return self._mutate(recommendation_id, _apply, skip_if=_unchanged)

    def record_executed_outcome(
        self,
        recommendation_id: str,
        *,
        exit_price: float,
        exit_reason: str = "manual",
        exit_date: str | None = None,
    ) -> dict[str, Any] | None:
        """Desfecho REAL: o preco que o dono digitou. Vence o contrafactual.

        Recusa linha que nao esteja marcada como executada. Nao e burocracia: se
        aceitasse, um desfecho contrafactual viraria "real" por omissao e a
        distincao que o aprendizado usa para separar dinheiro de simulacao
        evaporaria -- que e o defeito que esta caderneta existe para corrigir.
        """
        price = _as_float(exit_price)
        if price is None or price <= 0:
            raise LedgerError(f"Preco de saida executado invalido: {exit_price!r}")

        row = self.get(recommendation_id)
        if row is None:
            logger.warning("Recomendacao nao encontrada para desfecho: %s", recommendation_id)
            return None
        if row.get("executed") is not True:
            raise LedgerError(
                f"Recomendacao {recommendation_id} nao esta marcada como executada "
                f"(executed={row.get('executed')!r}). Marque a execucao primeiro "
                f"(mark_execution) -- desfecho real e desfecho contrafactual nao se misturam."
            )
        return self._apply_outcome(
            recommendation_id,
            exit_price=price,
            exit_reason=str(exit_reason or "manual"),
            exit_date=_iso_utc(exit_date) or datetime.now(UTC).isoformat(),
            source=OUTCOME_SOURCE_EXECUTED,
        )

    def _apply_outcome(
        self,
        recommendation_id: str,
        *,
        exit_price: float,
        exit_reason: str,
        exit_date: str,
        source: str,
        bars_held: int | None = None,
    ) -> dict[str, Any] | None:
        if source not in OUTCOME_SOURCES:  # pragma: no cover - guarda de contrato
            raise LedgerError(f"Origem de desfecho desconhecida: {source!r}")

        def _apply(row: dict[str, Any]) -> None:
            # Desfecho real NUNCA e sobrescrito por contrafactual: e a unica regra
            # de precedencia desta caderneta.
            if (
                source == OUTCOME_SOURCE_COUNTERFACTUAL
                and row.get("outcome_source") == OUTCOME_SOURCE_EXECUTED
            ):
                return
            if (
                source == OUTCOME_SOURCE_EXECUTED
                and row.get("outcome_source") == OUTCOME_SOURCE_COUNTERFACTUAL
            ):
                # Preserva o contrafactual para comparar "o que eu fiz" com "o que
                # teria acontecido" -- e a informacao que corrige o julgamento do dono.
                row["counterfactual"] = {
                    "outcome": row.get("outcome"),
                    "outcome_source": row.get("outcome_source"),
                    "exit_price": row.get("exit_price"),
                    "exit_date": row.get("exit_date"),
                    "exit_reason": row.get("exit_reason"),
                    "bars_held": row.get("bars_held"),
                    "pnl_amount": row.get("pnl_amount"),
                    "pnl_percent": row.get("pnl_percent"),
                }
            entry_price = _as_float(row.get("entry_price")) or 0.0
            shares = _as_float(row.get("shares") or row.get("qty")) or 0.0
            direction = normalize_direction(row.get("direction"))
            pnl_amount, pnl_percent = compute_pnl(
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                shares=shares,
            )
            row["exit_price"] = round(exit_price, 6)
            row["exit_date"] = exit_date
            row["exit_reason"] = exit_reason
            row["bars_held"] = bars_held
            row["pnl_amount"] = round(pnl_amount, 6)
            row["pnl_percent"] = round(pnl_percent, 6)
            row["outcome"] = _outcome_from_pnl(pnl_amount)
            row["outcome_source"] = source
            row["outcome_at"] = datetime.now(UTC).isoformat()

        return self._mutate(recommendation_id, _apply)

    def record_execution(
        self,
        recommendation_id: str,
        *,
        exit_price: float,
        exit_reason: str = "manual",
        executed_at: str | None = None,
        entry_price: float | None = None,
        note: str = "",
    ) -> dict[str, Any] | None:
        """Porta unica do dono: marca a execucao E registra o desfecho real.

        Existe para nao obrigar duas chamadas na ordem certa. `entry_price` e o
        preco efetivamente pago, que pode diferir do recomendado -- quando
        informado, passa a ser a base do PnL (e a recomendacao original fica em
        `entry_price_recommended`).
        """
        current = self.get(recommendation_id)
        if current is None:
            logger.warning("Recomendacao nao encontrada para execucao: %s", recommendation_id)
            return None
        if entry_price is not None:
            self._mutate(
                recommendation_id,
                lambda row: row.update(
                    {
                        "entry_price_recommended": row.get("entry_price_recommended")
                        or row.get("entry_price"),
                        "entry_price": _as_float(entry_price),
                    }
                ),
            )
        self.mark_execution(
            recommendation_id,
            executed=True,
            executed_at=executed_at,
            executed_price=entry_price,
            note=note,
        )
        return self.record_executed_outcome(
            recommendation_id,
            exit_price=exit_price,
            exit_reason=exit_reason,
        )

    # ── rotulagem contrafactual (o labeler) ───────────────────────────────────

    def label_counterfactuals(
        self,
        *,
        data_hub: Any = None,
        timeframe: str = "6M",
        now: datetime | None = None,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> LabelReport:
        """Rotula o que o MERCADO fez com as recomendacoes ainda sem desfecho.

        Usa `position_closer.evaluate_row` -- a MESMA avaliacao que fecha posicao.
        Duas implementacoes da barreira tripla divergiriam, e a divergencia
        apareceria exatamente onde doi: o contrafactual diria uma coisa e o
        fechamento real, outra.

        `dry_run=False` e o default AQUI, ao contrario do fechador, e a diferenca e
        deliberada: o fechador mexe em dinheiro e por isso nasce simulado; este
        rotulador escreve apenas na caderneta, nunca em posicao nem no journal. Uma
        caderneta que so se enche com o operador presente nao se enche -- e a
        caderneta vazia e a doenca que este modulo trata.

        Idempotente: linha rotulada deixa de estar pendente e nao e reavaliada.
        Linha com desfecho REAL jamais e tocada (a precedencia vive em
        `_apply_outcome`, nao aqui).
        """
        from core.trading import position_closer

        if data_hub is None:
            from data.data_hub import (
                hub as data_hub,
            )

            # Cache de ciclo, o mesmo do fechador: varias recomendacoes podem estar
            # no mesmo ETF e o fetch e por ticker, nao por linha.
            data_hub = position_closer._CandleCache(data_hub)

        pending = [row for row in self._read_all() if row.get("outcome") is None]
        if limit is not None:
            pending = pending[: max(0, int(limit))]

        decisions: list[dict[str, Any]] = []
        skipped: dict[str, int] = {}
        labeled = 0

        for row in pending:
            recommendation_id = str(row.get("recommendation_id") or "")
            try:
                decision = position_closer.evaluate_row(row, data_hub=data_hub, timeframe=timeframe)
            except Exception as exc:
                logger.exception("Falha ao avaliar recomendacao %s", recommendation_id)
                reason = f"error:{type(exc).__name__}"
                skipped[reason] = skipped.get(reason, 0) + 1
                decisions.append(
                    {"recommendation_id": recommendation_id, "status": "skipped", "reason": reason}
                )
                continue

            is_label = decision.status == position_closer.STATUS_WOULD_CLOSE
            reason = "labeled" if is_label else str(decision.reason)
            skipped[reason] = skipped.get(reason, 0) + 1
            decisions.append(
                {
                    "recommendation_id": recommendation_id,
                    "ticker": decision.ticker,
                    "status": "labeled" if is_label else "pending",
                    "reason": reason,
                    "outcome": decision.exit_reason if is_label else None,
                    "exit_price": decision.exit_price if is_label else None,
                }
            )
            if is_label and dry_run:
                continue
            if is_label:
                self._apply_outcome(
                    recommendation_id,
                    exit_price=float(decision.exit_price or 0.0),
                    exit_reason=str(decision.exit_reason),
                    exit_date=_iso_utc(decision.exit_timestamp)
                    or (now or datetime.now(UTC)).isoformat(),
                    source=OUTCOME_SOURCE_COUNTERFACTUAL,
                    bars_held=decision.bars_held,
                )
                labeled += 1
            else:
                # Diagnostico do SILENCIO: por que esta recomendacao ainda nao tem
                # desfecho. Sem isto, pendencia e indistinguivel de esquecimento.
                self._mutate(
                    recommendation_id,
                    lambda r, reason=reason: r.update(
                        {
                            "last_label_reason": reason,
                            "last_labeled_at": datetime.now(UTC).isoformat(),
                        }
                    ),
                    skip_if=lambda r, reason=reason: r.get("last_label_reason") == reason,
                )

        report = LabelReport(
            dry_run=dry_run,
            evaluated=len(pending),
            labeled=labeled,
            pending=len(pending) - labeled,
            skipped_reasons=skipped,
            decisions=decisions,
        )
        logger.info(
            "recommendation_ledger_label dry_run=%s evaluated=%d labeled=%d pending=%d",
            dry_run,
            report.evaluated,
            report.labeled,
            report.pending,
        )
        return report

    # ── leitura ───────────────────────────────────────────────────────────────

    def get(self, recommendation_id: str) -> dict[str, Any] | None:
        for entry in self._read_all():
            if entry.get("recommendation_id") == recommendation_id:
                return entry
        return None

    def list_all(self) -> list[dict[str, Any]]:
        return self._read_all()

    def list_pending(self) -> list[dict[str, Any]]:
        """Sem desfecho ainda -- nem real, nem contrafactual."""
        return [row for row in self._read_all() if row.get("outcome") is None]

    def list_resolved(self) -> list[dict[str, Any]]:
        return [row for row in self._read_all() if row.get("outcome") in TERMINAL_OUTCOMES]

    def list_executed(self) -> list[dict[str, Any]]:
        return [row for row in self._read_all() if row.get("executed") is True]

    def list_unexecuted(self) -> list[dict[str, Any]]:
        return [row for row in self._read_all() if row.get("executed") is False]

    def list_awaiting_owner(self) -> list[dict[str, Any]]:
        """Recomendacoes que o dono ainda nao marcou (executada = desconhecido).

        E a fila de trabalho dele: o sistema recomendou e ninguem disse o que fez.
        """
        return [row for row in self._read_all() if row.get("executed") is None]

    def as_learning_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Traduz a linha da caderneta para o formato que os MOTORES ja leem.

        `OutcomeLearningEngine.process_trade` (outcome_learning.py:167) le
        `trade_id`, `outcome`, `exit_price`, `exit_date`, `entry_price`, `shares`,
        `direction` e `expert_predictions`. Nenhum motor e reescrito: a unica
        traducao e de NOME DE CAMPO, e vive aqui, num lugar so.
        """
        return {
            **row,
            "trade_id": str(row.get("recommendation_id") or row.get("trade_id") or ""),
            "ticker": str(row.get("ticker") or row.get("symbol") or "").upper(),
            "shares": _as_float(row.get("shares") or row.get("qty")) or 0.0,
            "direction": str(row.get("direction") or "").lower(),
        }

    def learning_rows(self, *, include_counterfactual: bool = False) -> list[dict[str, Any]]:
        """Desfechos prontos para o aprendizado, no formato dos motores.

        DEFAULT: so desfecho REAL (executado). Aprendizado e sobre dinheiro que
        existiu; deixar o contrafactual entrar por omissao faria o motor de pesos
        aprender com trades que ninguem fez -- o defeito do paper order, de novo.
        Quem quer aprendizado-sombra passa `include_counterfactual=True` e recebe
        `outcome_source` em cada linha para separar depois.
        """
        rows = []
        for row in self.list_resolved():
            source = str(row.get("outcome_source") or "")
            if source == OUTCOME_SOURCE_COUNTERFACTUAL and not include_counterfactual:
                continue
            rows.append(self.as_learning_row(row))
        return rows

    def stats(self) -> dict[str, Any]:
        """Placar da caderneta. O numero que importa e `missed_winners`."""
        rows = self._read_all()
        resolved = [r for r in rows if r.get("outcome") in TERMINAL_OUTCOMES]
        executed = [r for r in rows if r.get("executed") is True]
        unexecuted = [r for r in rows if r.get("executed") is False]

        real = [r for r in resolved if r.get("outcome_source") == OUTCOME_SOURCE_EXECUTED]
        shadow = [r for r in resolved if r.get("outcome_source") == OUTCOME_SOURCE_COUNTERFACTUAL]

        def _wins(items: Sequence[Mapping[str, Any]]) -> int:
            return sum(1 for r in items if r.get("outcome") == OUTCOME_WIN)

        missed_winners = [r for r in unexecuted if r.get("outcome") == OUTCOME_WIN]
        avoided_losers = [r for r in unexecuted if r.get("outcome") == OUTCOME_LOSS]
        return {
            "total": len(rows),
            "pending": len(rows) - len(resolved),
            "resolved": len(resolved),
            "executed_yes": len(executed),
            "executed_no": len(unexecuted),
            "executed_unknown": len(rows) - len(executed) - len(unexecuted),
            "outcomes_executed": len(real),
            "outcomes_counterfactual": len(shadow),
            "wins_executed": _wins(real),
            "wins_counterfactual": _wins(shadow),
            "missed_winners": len(missed_winners),
            "avoided_losers": len(avoided_losers),
            "not_actionable": sum(1 for r in rows if not (r.get("barriers") or {}).get("stop")),
            "path": str(self._path),
            "storage_environment": self._storage_environment,
        }


_default_ledger: RecommendationLedger | None = None
_default_lock = threading.Lock()


def get_recommendation_ledger() -> RecommendationLedger:
    """Caderneta de processo (mesmo padrao de `get_feedback_loop`)."""
    global _default_ledger
    with _default_lock:
        if _default_ledger is None:
            _default_ledger = RecommendationLedger()
        return _default_ledger


def record_recommendation_for_trade(
    *,
    ticker: str,
    action: str,
    qty: float,
    entry_price: float,
    barriers: Mapping[str, Any] | None = None,
    rationale: str = "",
    expert_source: str = "",
    verdict_at_entry: str = "",
    learning_context: Mapping[str, Any] | None = None,
    expected_holding_period: str = "unknown",
    run_id: str = "",
    ledger: RecommendationLedger | None = None,
) -> RecordResult | None:
    """Atalho para o pipeline: registra a recomendacao a partir do que ele ja tem.

    Devolve `None` (e apenas loga) quando a recomendacao nao pode ser registrada.
    E deliberado: a caderneta e trilho de aprendizado, nao portao -- falhar ao
    gravar uma recomendacao nunca pode derrubar o ciclo que a produziu. A emissao
    perdida fica visivel no log, que e onde ela tem que aparecer.
    """
    ledger = ledger or get_recommendation_ledger()
    try:
        recommendation = Recommendation(
            ticker=ticker,
            direction=action,
            entry_price=entry_price,
            shares=qty,
            rationale=rationale,
            expert_source=expert_source,
            expected_holding_period=expected_holding_period,
            run_id=run_id,
            stop_loss_price=(barriers or {}).get("stop_loss_price"),
            take_profit_price=(barriers or {}).get("take_profit_price"),
            time_horizon_bars=(barriers or {}).get("time_horizon_bars"),
            thesis=rationale,
            # `FeedbackLoop.analyze_confidence_bias` (feedback_loop.py:760) le a
            # confianca daqui. Verbatim do que o journal grava, para o motor ler a
            # caderneta sem saber que ela e outra coisa.
            verdict_at_entry=verdict_at_entry,
            expert_predictions=dict((learning_context or {}).get("expert_predictions") or {}),
            expert_attribution=dict((learning_context or {}).get("expert_attribution") or {}),
            confidence_at_entry=(learning_context or {}).get("confidence_at_entry"),
            prediction_probability_at_entry=(learning_context or {}).get(
                "prediction_probability_at_entry"
            ),
            prediction_class_at_entry=(learning_context or {}).get("prediction_class_at_entry"),
            calibration_status=str((learning_context or {}).get("calibration_status") or "unknown"),
            model_id=str((learning_context or {}).get("model_id") or ""),
            forecast_as_of=str((learning_context or {}).get("forecast_as_of") or ""),
            forecast_horizon=(learning_context or {}).get("forecast_horizon"),
            risk_at_entry=(learning_context or {}).get("risk_at_entry"),
            tags=["recommendation"],
        )
        return ledger.record(recommendation)
    except Exception as exc:  # noqa: BLE001 — trilho de aprendizado nao derruba pipeline
        logger.warning(
            "recommendation_ledger_record_failed ticker=%s error=%s", ticker, str(exc)[:200]
        )
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Porta de entrada do dono (CLI)
# ──────────────────────────────────────────────────────────────────────────────


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recommendation_ledger",
        description=(
            "Caderneta de recomendacoes do SuperEzio. O dono e o atuador: aqui ele "
            "marca o que executou e a que preco."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lista a fila: o que o sistema recomendou e voce ainda nao marcou.")
    sub.add_parser("stats", help="Placar da caderneta (inclui missed_winners).")
    sub.add_parser("label", help="Rotula o contrafactual das recomendacoes pendentes.")

    mark = sub.add_parser("mark", help="Marca execucao (e, opcionalmente, o desfecho real).")
    mark.add_argument("recommendation_id")
    mark.add_argument(
        "--executed",
        choices=["yes", "no", "unknown"],
        required=True,
        help="yes = executei | no = nao executei | unknown = nao sei / desmarcar",
    )
    mark.add_argument("--entry-price", type=float, default=None, help="Preco efetivamente pago.")
    mark.add_argument("--exit-price", type=float, default=None, help="Preco efetivamente vendido.")
    mark.add_argument("--exit-reason", default="manual")
    mark.add_argument("--note", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    ledger = RecommendationLedger()

    if args.command == "list":
        for row in ledger.list_awaiting_owner():
            print(
                f"{row.get('recommendation_id')}  {row.get('ticker')} {row.get('direction')} "
                f"entrada={row.get('entry_price')} stop={row.get('stop_loss_price')} "
                f"alvo={row.get('take_profit_price')}  {row.get('rationale') or ''}"
            )
        return 0

    if args.command == "stats":
        print(json.dumps(ledger.stats(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "label":
        report = ledger.label_counterfactuals()
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    executed = {"yes": True, "no": False, "unknown": None}[args.executed]
    if executed is True and args.exit_price is not None:
        row = ledger.record_execution(
            args.recommendation_id,
            exit_price=args.exit_price,
            exit_reason=args.exit_reason,
            entry_price=args.entry_price,
            note=args.note,
        )
    else:
        row = ledger.mark_execution(
            args.recommendation_id,
            executed=executed,
            executed_price=args.entry_price,
            note=args.note,
        )
    if row is None:
        print(f"Recomendacao nao encontrada: {args.recommendation_id}")
        return 1
    print(json.dumps(row, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - entrada de linha de comando
    with contextlib.suppress(KeyboardInterrupt):
        raise SystemExit(main())


__all__ = [
    "DEFAULT_LEDGER_PATH",
    "DIRECTION_LONG",
    "DIRECTION_SHORT",
    "OUTCOME_SOURCE_COUNTERFACTUAL",
    "OUTCOME_SOURCE_EXECUTED",
    "LabelReport",
    "LedgerError",
    "Recommendation",
    "RecommendationLedger",
    "RecordResult",
    "build_recommendation_id",
    "compute_pnl",
    "get_recommendation_ledger",
    "main",
    "normalize_direction",
    "record_recommendation_for_trade",
]
