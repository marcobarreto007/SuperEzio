"""Performance Metrics - C7: Aprender com acertos e erros.

Calcula metricas quantitativas sobre o journal de trades paper:
Sharpe ratio, max drawdown, win rate, profit factor, expectancy,
e calibracao de tese (thesis vs outcome).

Totalmente offline - opera sobre PaperJournal.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .paper_journal import PaperJournal

logger = logging.getLogger(__name__)


@dataclass
class PerformanceReport:
    """Relatorio completo de performance do portfolio paper."""

    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Baseline
    total_trades: int = 0
    closed_trades: int = 0
    open_trades: int = 0

    # Returns
    total_pnl: float = 0.0
    total_pnl_percent: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_percent: float = 0.0
    avg_loss_percent: float = 0.0

    # Ratios
    win_rate_pct: float = 0.0
    loss_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    expectancy_percent: float = 0.0

    # Risk
    max_drawdown_percent: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0

    # Qualidade de tese
    thesis_accuracy_pct: float = 0.0
    avg_holding_days: float = 0.0
    trades_with_reflection: int = 0
    reflection_rate_pct: float = 0.0

    # Vieses detectados
    detected_biases: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa para JSON, arredondando floats."""
        result = {}
        for key, value in self.__dict__.items():
            if isinstance(value, float):
                result[key] = round(value, 4)
            else:
                result[key] = value
        return result


class PerformanceEngine:
    """Calcula metricas de performance a partir do PaperJournal."""

    def __init__(self, journal: PaperJournal, initial_equity: float | None = None):
        self._journal = journal
        if initial_equity is None:
            from core.mission_context import get_mission_equity
            initial_equity = get_mission_equity()
        self._initial_equity = initial_equity

    def evaluate(self) -> PerformanceReport:
        """Gera relatorio completo de performance."""
        report = PerformanceReport()
        closed = self._journal.list_closed()
        all_trades = self._journal.list_all()

        report.total_trades = len(all_trades)
        report.closed_trades = len(closed)
        report.open_trades = len(self._journal.list_open())

        if not closed:
            report.detected_biases.append(
                "insufficient_data: fewer than 1 closed trade - cannot compute metrics"
            )
            report.improvement_suggestions.append(
                "Execute at least 10 paper trades before drawing conclusions."
            )
            return report

        # Returns
        pnls = [t.get("pnl_amount", 0) or 0 for t in closed]
        pnl_pcts = [t.get("pnl_percent", 0) or 0 for t in closed]

        report.total_pnl = sum(pnls)
        report.total_pnl_percent = (
            (report.total_pnl / self._initial_equity * 100) if self._initial_equity > 0 else 0
        )

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_pcts = [
            t.get("pnl_percent", 0) or 0 for t in closed if (t.get("pnl_amount", 0) or 0) > 0
        ]
        loss_pcts = [
            t.get("pnl_percent", 0) or 0 for t in closed if (t.get("pnl_amount", 0) or 0) < 0
        ]

        report.avg_win = sum(wins) / len(wins) if wins else 0
        report.avg_loss = sum(losses) / len(losses) if losses else 0
        report.avg_win_percent = sum(win_pcts) / len(win_pcts) if win_pcts else 0
        report.avg_loss_percent = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0

        # Ratios
        total_wins = len(wins)
        total_losses = len(losses)
        report.win_rate_pct = (total_wins / len(closed) * 100) if closed else 0
        report.loss_rate_pct = (total_losses / len(closed) * 100) if closed else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        report.profit_factor = (
            (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
        )

        report.expectancy = (report.win_rate_pct / 100 * report.avg_win) + (
            report.loss_rate_pct / 100 * report.avg_loss
        )
        report.expectancy_percent = (report.win_rate_pct / 100 * report.avg_win_percent) + (
            report.loss_rate_pct / 100 * report.avg_loss_percent
        )

        # Drawdown
        report.max_drawdown_percent = self._calc_max_drawdown(closed)

        # Sharpe / Sortino (sobre % returns)
        if len(pnl_pcts) >= 2:
            report.sharpe_ratio = self._calc_sharpe(pnl_pcts)
            report.sortino_ratio = self._calc_sortino(pnl_pcts)
        else:
            report.sharpe_ratio = 0.0
            report.sortino_ratio = 0.0

        # Thesis quality
        with_reflection = [t for t in closed if t.get("lesson_learned")]
        report.trades_with_reflection = len(with_reflection)
        report.reflection_rate_pct = (len(with_reflection) / len(closed) * 100) if closed else 0

        thesis_correct = sum(1 for t in closed if t.get("thesis_correct") is True)
        thesis_wrong = sum(1 for t in closed if t.get("thesis_correct") is False)
        report.thesis_accuracy_pct = (
            thesis_correct / (thesis_correct + thesis_wrong) * 100
            if (thesis_correct + thesis_wrong) > 0
            else 0
        )

        # Holding period
        report.avg_holding_days = self._calc_avg_holding(closed)

        # Bias detection
        report.detected_biases = self._detect_biases(closed, report)
        report.improvement_suggestions = self._suggest_improvements(closed, report)

        return report

    # Internal calculators

    def _calc_max_drawdown(self, closed: list[dict[str, Any]]) -> float:
        """Calcula max drawdown percentual acumulado."""
        pnls = [t.get("pnl_amount", 0) or 0 for t in closed]
        if not pnls:
            return 0.0

        equity_curve = [self._initial_equity]
        for pnl in pnls:
            equity_curve.append(equity_curve[-1] + pnl)

        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 2)

    def _calc_sharpe(self, returns_pct: list[float], risk_free_annual: float = 4.0) -> float:
        """Sharpe ratio anualizado simplificado."""
        if len(returns_pct) < 2:
            return 0.0
        mean_ret = sum(returns_pct) / len(returns_pct)
        variance = (
            sum((r - mean_ret) ** 2 for r in returns_pct) / (len(returns_pct) - 1)
            if len(returns_pct) > 1
            else 0
        )
        std_ret = math.sqrt(variance) if variance > 0 else 0
        if std_ret == 0:
            return 0.0
        # Assumindo ~252 trades/ano para anualizacao simplificada
        annual_factor = math.sqrt(min(len(returns_pct), 252))
        excess = mean_ret - (risk_free_annual / 252)
        return round((excess / std_ret) * annual_factor, 4)

    def _calc_sortino(self, returns_pct: list[float], risk_free_annual: float = 4.0) -> float:
        """Sortino ratio (usa apenas desvio negativo)."""
        if len(returns_pct) < 2:
            return 0.0
        mean_ret = sum(returns_pct) / len(returns_pct)
        downside = [min(0, r - (risk_free_annual / 252)) for r in returns_pct]
        downside_sq = [d**2 for d in downside]
        downside_var = sum(downside_sq) / (len(downside_sq) - 1) if len(downside_sq) > 1 else 0
        downside_std = math.sqrt(downside_var) if downside_var > 0 else 0
        if downside_std == 0:
            return 0.0
        annual_factor = math.sqrt(min(len(returns_pct), 252))
        excess = mean_ret - (risk_free_annual / 252)
        return round((excess / downside_std) * annual_factor, 4)

    def _calc_avg_holding(self, closed: list[dict[str, Any]]) -> float:
        """Tempo medio de holding em dias."""
        durations = []
        for t in closed:
            entry_str = t.get("entry_date", "")
            exit_str = t.get("exit_date", "")
            if entry_str and exit_str:
                try:
                    entry = datetime.fromisoformat(entry_str.replace("Z", "+00:00"))
                    exit_dt = datetime.fromisoformat(exit_str.replace("Z", "+00:00"))
                    durations.append((exit_dt - entry).total_seconds() / 86400)
                except (ValueError, TypeError):
                    pass
        return round(sum(durations) / len(durations), 2) if durations else 0.0

    # Bias detection

    def _detect_biases(self, closed: list[dict[str, Any]], report: PerformanceReport) -> list[str]:
        """Detecta vieses sistematicos nos trades."""
        biases: list[str] = []

        if report.closed_trades < 5:
            biases.append(
                "insufficient_sample: menos de 5 trades fechados - metricas nao sao estatisticamente significativas"
            )
            return biases

        # Vies 1: Cut winners short, let losers run
        if report.avg_loss_percent < 0 and report.avg_win_percent > 0:
            if abs(report.avg_loss_percent) > report.avg_win_percent * 1.5:
                biases.append(
                    f"losers_outpace_winners: perda media ({report.avg_loss_percent:.2f}%) e "
                    f"{abs(report.avg_loss_percent / max(report.avg_win_percent, 0.01)):.1f}x "
                    f"maior que ganho medio ({report.avg_win_percent:.2f}%). "
                    f"Considere stops mais apertados ou deixar vencedores correrem mais."
                )

        # Vies 2: Thesis consistently wrong
        if report.thesis_accuracy_pct < 40 and report.closed_trades >= 5:
            biases.append(
                f"thesis_accuracy_low: apenas {report.thesis_accuracy_pct:.0f}% das teses se confirmaram. "
                f"Revisar processo de geracao de tese - pode estar superestimando catalysts ou ignorando riscos sistemicos."
            )

        # Vies 3: No reflections
        if report.reflection_rate_pct < 50 and report.closed_trades >= 5:
            biases.append(
                f"low_reflection_rate: apenas {report.reflection_rate_pct:.0f}% dos trades tem reflexao post-mortem. "
                f"Sem reflexao, nao ha aprendizado. Documentar toda saida."
            )

        # Vies 4: Win rate > 70% but negative expectancy (many small wins, few big losses)
        if report.win_rate_pct > 70 and report.expectancy < 0:
            biases.append(
                f"high_win_rate_negative_expectancy: {report.win_rate_pct:.0f}% win rate mas expectancy negativa "
                f"({report.expectancy:.2f}). Muitos ganhos pequenos e poucas perdas grandes - "
                f"vies classico de 'cut winners short, let losers run'."
            )

        # Vies 5: Profit factor below 1
        if report.profit_factor < 1.0 and report.closed_trades >= 5:
            biases.append(
                f"profit_factor_below_1: profit factor = {report.profit_factor:.2f}. "
                f"Perdas superam ganhos. Sistema nao e rentavel no estado atual."
            )

        return biases

    def _suggest_improvements(
        self, closed: list[dict[str, Any]], report: PerformanceReport
    ) -> list[str]:
        """Sugere melhorias baseadas nos vieses detectados."""
        suggestions: list[str] = []

        if report.closed_trades < 5:
            suggestions.append("Execute pelo menos 10 trades paper antes de otimizar a estrategia.")
            return suggestions

        # Sugestoes baseadas em vieses
        if report.avg_loss_percent < 0 and report.avg_win_percent > 0:
            if abs(report.avg_loss_percent) > report.avg_win_percent * 1.5:
                suggestions.append(
                    "Implementar stop-loss mais rigido (ex: -5%% ou -2x ATR) e trailing stop nos vencedores."
                )

        if report.thesis_accuracy_pct < 50:
            suggestions.append(
                "Revisar o processo de tese: adicionar mais dados fundamentalistas, "
                "confirmar catalysts com multiplas fontes, e exigir confirmacao tecnica antes da entrada."
            )

        if report.reflection_rate_pct < 80:
            suggestions.append(
                "Criar habito de documentar reflexao em todo trade fechado. "
                "Usar scripts/paper_journal_cli.py reflect <trade_id> apos cada saida."
            )

        if report.win_rate_pct < 40:
            suggestions.append(
                f"Win rate baixa ({report.win_rate_pct:.0f}%). "
                f"Refinar criterios de entrada: adicionar filtro de liquidez, "
                f"exigir alinhamento tecnico + fundamentalista, evitar entradas em mercados laterais."
            )

        if report.sharpe_ratio < 0:
            suggestions.append(
                f"Sharpe negativo ({report.sharpe_ratio:.2f}). "
                f"Retorno nao compensa o risco. Reduzir tamanho de posicao ou revisar estrategia completamente."
            )

        if report.max_drawdown_percent > 20:
            suggestions.append(
                f"Drawdown elevado ({report.max_drawdown_percent:.1f}%). "
                f"Implementar limite de perda diaria/semanal e reduzir correlacao entre posicoes."
            )

        if not suggestions:
            suggestions.append("Metricas dentro do esperado. Continuar monitorando e refinando.")

        return suggestions
