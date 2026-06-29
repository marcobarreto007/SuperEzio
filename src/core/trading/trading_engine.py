"""Trading Engine - Cérebro autônomo de trading do Bob.

O motor que:
1. Scaneia o mercado em busca de oportunidades
2. Delibera com o comitê
3. Executa trades com todos os gates
4. Gerencia posições abertas
5. Aprende com cada resultado
6. Repete 24/7

Bob agora é um organismo que vive no mercado.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Importar todos os componentes
from .xp_system import get_xp_system
from .auto_executor import get_auto_executor, ExecutionStatus
from .position_manager import get_position_manager, PositionSide, ExitReason
from .risk_guard import get_risk_guard
from .committee import get_reflection_committee
from .pain_memory import get_pain_memory
from .paper_journal import PaperJournal


class MarketSentiment(Enum):
    """Sentimento de mercado."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    VOLATILE = "volatile"


@dataclass
class TradingOpportunity:
    """Uma oportunidade de trading identificada."""

    symbol: str
    sentiment: MarketSentiment
    confidence: float  # 0-1
    entry_price: float
    stop_loss: float
    take_profit: float
    thesis: str
    expected_move_pct: float
    liquidity_score: float  # 0-1
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sentiment": self.sentiment.value,
            "confidence": round(self.confidence, 3),
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "take_profit": round(self.take_profit, 2),
            "thesis": self.thesis,
            "expected_move_pct": round(self.expected_move_pct, 3),
            "liquidity_score": round(self.liquidity_score, 3),
            "timestamp": self.timestamp,
        }


@dataclass
class TradingSession:
    """Sessão de trading."""

    session_id: str
    start_time: str
    end_time: str | None = None
    opportunities_scanned: int = 0
    trades_executed: int = 0
    trades_won: int = 0
    trades_lost: int = 0
    total_pnl: float = 0.0
    xp_gained: int = 0
    lessons_learned: int = 0
    decisions_made: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "opportunities_scanned": self.opportunities_scanned,
            "trades_executed": self.trades_executed,
            "trades_won": self.trades_won,
            "trades_lost": self.trades_lost,
            "win_rate": round(self.trades_won / max(1, self.trades_executed), 3),
            "total_pnl": round(self.total_pnl, 2),
            "xp_gained": self.xp_gained,
            "lessons_learned": self.lessons_learned,
            "decisions": self.decisions_made[-10:],  # Últimas 10 decisões
        }


class TradingEngine:
    """Motor de trading autônomo do Bob.

    Fluxo contínuo:
    1. Scanear mercado (encontrar oportunidades)
    2. Para cada oportunidade:
       a. Checar risk guard
       b. Consultar committee
       c. Calcular position size
       d. Executar se aprovado
    3. Gerenciar posições abertas
    4. Registrar resultados
    5. Aprender (XP, pain memory, feedback)
    6. Repetir
    """

    def __init__(
        self,
        equity: float = 10000.0,
        journal_path: Path | None = None,
        persistence_path: Path | None = None,
        watchlist: list[str] | None = None,
    ):
        self.equity = equity
        self._journal_path = journal_path or Path("data/paper_journal.jsonl")
        self._persistence_path = persistence_path or Path("data/trading_engine_state.json")
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Inicializar componentes
        self._xp_system = get_xp_system()
        self._executor = get_auto_executor(equity=equity)
        self._position_manager = get_position_manager(equity=equity)
        self._risk_guard = get_risk_guard(equity=equity)
        self._committee = get_reflection_committee()
        self._pain_memory = get_pain_memory()
        self._journal = PaperJournal()

        # Dynamic watchlist — pulls from investor DB + market context
        if watchlist is None:
            from .dynamic_watchlist import get_dynamic_watchlist as _get_dynamic_watchlist

            watchlist = _get_dynamic_watchlist()
        self._watchlist: list[str] = watchlist
        logger.info("trading_engine_watchlist_loaded", count=len(self._watchlist))

        # Estado
        self._session: TradingSession | None = None
        self._last_scan_time: float = 0
        self._scan_interval_seconds: int = 30  # Scan a cada 30s durante mercado
        self._opportunities_found: list[TradingOpportunity] = []

        # Métricas
        self._total_trades = 0
        self._total_wins = 0
        self._total_losses = 0
        self._total_pnl = 0.0

        # Carregar estado anterior
        self._load_state()

    def _load_state(self) -> None:
        """Carrega estado persistido."""
        if self._persistence_path.exists():
            try:
                with open(self._persistence_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self._total_trades = state.get("total_trades", 0)
                    self._total_wins = state.get("total_wins", 0)
                    self._total_losses = state.get("total_losses", 0)
                    self._total_pnl = state.get("total_pnl", 0.0)
                    logger.info(
                        "State loaded: %d trades, PnL: $%.2f", self._total_trades, self._total_pnl
                    )
            except Exception as e:
                logger.warning("Failed to load state: %s", e)

    def _save_state(self) -> None:
        """Salva estado em disco."""
        try:
            state = {
                "total_trades": self._total_trades,
                "total_wins": self._total_wins,
                "total_losses": self._total_losses,
                "total_pnl": round(self._total_pnl, 2),
                "equity": round(self.equity, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save state: %s", e)

    def start_session(self) -> TradingSession:
        """Inicia uma nova sessão de trading."""
        session_id = f"session-{int(time.time())}"
        self._session = TradingSession(
            session_id=session_id,
            start_time=datetime.now(timezone.utc).isoformat(),
        )
        logger.info("Session started: %s", session_id)
        return self._session

    def end_session(self) -> TradingSession:
        """Finaliza sessão atual."""
        if self._session:
            self._session.end_time = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Session ended: %d trades, PnL: $%.2f, Win rate: %.1f%%",
                self._session.trades_executed,
                self._session.total_pnl,
                self._session.trades_won / max(1, self._session.trades_executed) * 100,
            )
        return self._session

    def scan_market(self) -> list[TradingOpportunity]:
        """Scaneia mercado em busca de oportunidades.

        Em produção, isso usaria dados reais. Aqui simula com base em:
        - Tendências aleatórias (com viés realista)
        - Níveis de suporte/resistência simulados
        - Volatilidade
        """
        opportunities = []

        for symbol in self._watchlist:
            # Simular dados de mercado
            base_price = self._get_simulated_price(symbol)

            # Gerar sentimentos baseados em "indicadores" simulados
            # Em produção, viriam de análise técnica/fundamentalista real
            sentiment_roll = random.random()

            if sentiment_roll < 0.25:
                sentiment = MarketSentiment.BULLISH
                confidence = random.uniform(0.6, 0.85)
                entry_price = base_price
                stop_loss = base_price * (1 - 0.02)  # 2% stop
                take_profit = base_price * (1 + random.uniform(0.03, 0.06))  # 3-6% alvo
                thesis = (
                    f"Tendência de alta confirmada, rompimento de resistencia em ${entry_price:.2f}"
                )
            elif sentiment_roll < 0.5:
                sentiment = MarketSentiment.BEARISH
                confidence = random.uniform(0.6, 0.85)
                entry_price = base_price
                stop_loss = base_price * (1 + 0.02)
                take_profit = base_price * (1 - random.uniform(0.03, 0.06))
                thesis = f"Tendencia de baixa, suporte quebrado em ${entry_price:.2f}"
            else:
                continue  # Neutral, skip

            # Checar pain memory
            pain_risk = self._pain_memory.check_setup_risk(
                {
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                }
            )

            # Se dor for muito alta, pular
            if pain_risk.get("level") == "SEVERE":
                logger.info("Skipping %s due to severe pain memory", symbol)
                continue

            # Calcular liquidez (simulada)
            liquidity_score = random.uniform(0.7, 0.95)

            opp = TradingOpportunity(
                symbol=symbol,
                sentiment=sentiment,
                confidence=confidence * (0.8 if pain_risk.get("level") == "HIGH" else 1.0),
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                thesis=thesis,
                expected_move_pct=abs(take_profit - entry_price) / entry_price,
                liquidity_score=liquidity_score,
            )
            opportunities.append(opp)

        self._opportunities_found = opportunities
        return opportunities

    def _get_simulated_price(self, symbol: str) -> float:
        """Retorna preço simulado para um símbolo."""
        # Preços base aproximados (simulação)
        base_prices = {
            "AAPL": 190.0,
            "SPY": 510.0,
            "TLT": 95.0,
            "GLD": 190.0,
            "QQQ": 440.0,
            "IWM": 200.0,
        }
        base = base_prices.get(symbol, 100.0)
        # Adicionar variação aleatória
        return base * random.uniform(0.98, 1.02)

    def evaluate_opportunity(self, opp: TradingOpportunity) -> dict[str, Any]:
        """Avalia uma oportunidade e decide se deve executar.

        Retorna decisão completa com todos os fatores.
        """
        decision = {
            "opportunity": opp.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluated": True,
            "approved": False,
            "rejection_reason": None,
            "factors": {},
        }

        # 1. Risk guard check
        side = "buy" if opp.sentiment == MarketSentiment.BULLISH else "sell"
        risk_result = self._risk_guard.check_trade(
            symbol=opp.symbol,
            side=side,
            quantity=10,  # Placeholder, será calculado depois
            entry_price=opp.entry_price,
            stop_loss=opp.stop_loss,
            market_data={"avg_daily_volume": 50_000_000},
        )
        decision["factors"]["risk_guard"] = risk_result.to_dict()

        if not risk_result.approved:
            decision["approved"] = False
            decision["rejection_reason"] = "risk_guard"
            return decision

        # 2. Committee deliberation
        setup = {
            "ticker": opp.symbol,
            "side": side,
            "entry_price": opp.entry_price,
            "stop_loss": opp.stop_loss,
            "take_profit": opp.take_profit,
            "thesis": opp.thesis,
            "confidence": opp.confidence,
            "expected_move_pct": opp.expected_move_pct,
        }
        committee_decision = self._committee.deliberate(setup)
        decision["factors"]["committee"] = {
            "consensus": committee_decision.consensus.value,
            "is_approved": committee_decision.is_approved,
            "approval_rate": round(committee_decision.approval_rate, 3),
            "reasoning": committee_decision.reasoning_summary[:200],
        }

        if not committee_decision.is_approved:
            decision["approved"] = False
            decision["rejection_reason"] = "committee"
            return decision

        # 3. Aprovado!
        decision["approved"] = True
        decision["recommended_quantity"] = self._calculate_recommended_quantity(opp)

        return decision

    def _calculate_recommended_quantity(self, opp: TradingOpportunity) -> int:
        """Calcula quantidade recomendada baseado em risco."""
        risk_per_share = abs(opp.entry_price - opp.stop_loss)
        max_risk_amount = self.equity * 0.02  # 2% de risco
        shares_by_risk = int(max_risk_amount / risk_per_share)

        # Limitar a 10% do equity
        max_position_value = self.equity * 0.10
        shares_by_position = int(max_position_value / opp.entry_price)

        return min(shares_by_risk, shares_by_position)

    def execute_trade(self, opp: TradingOpportunity, quantity: int) -> dict[str, Any] | None:
        """Executa um trade.

        Returns:
            Resultado da execução ou None se falhou
        """
        side = "buy" if opp.sentiment == MarketSentiment.BULLISH else "sell"
        position_side = PositionSide.LONG if side == "buy" else PositionSide.SHORT

        # Preparar ordem com todos os gates
        request = self._executor.prepare_order(
            symbol=opp.symbol,
            side=side,
            quantity=quantity,
            entry_price=opp.entry_price,
            stop_loss=opp.stop_loss,
            take_profit=opp.take_profit,
            thesis=opp.thesis,
            confidence=opp.confidence,
        )

        # Se não aprovado, retornar
        if request.status != ExecutionStatus.APPROVED:
            logger.warning("Trade rejected: %s - %s", opp.symbol, request.rejection_reason)
            return None

        # Executar
        executed = self._executor.execute_order(request)

        if executed.status != ExecutionStatus.EXECUTED:
            logger.error("Execution failed: %s", opp.symbol)
            return None

        # Criar posição no position manager
        position = self._position_manager.open_position(
            symbol=opp.symbol,
            side=position_side,
            quantity=quantity,
            entry_price=opp.entry_price,
            stop_loss=opp.stop_loss,
            take_profit=opp.take_profit,
            thesis=opp.thesis,
            confidence=opp.confidence,
        )

        logger.info(
            "TRADE EXECUTED: %s %s %d shares @ $%.2f | SL: $%.2f | TP: $%.2f",
            side.upper(),
            opp.symbol,
            quantity,
            opp.entry_price,
            opp.stop_loss,
            opp.take_profit,
        )

        # Atualizar contadores
        self._total_trades += 1
        if self._session:
            self._session.trades_executed += 1

        # Registrar no journal
        self._journal.add_trade(
            {
                "trade_id": position.position_id,
                "symbol": opp.symbol,
                "side": side,
                "quantity": quantity,
                "entry_price": opp.entry_price,
                "stop_loss": opp.stop_loss,
                "take_profit": opp.take_profit,
                "thesis": opp.thesis,
                "verdict_at_entry": f"Confidence {opp.confidence * 100:.0f}%",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        return {
            "position_id": position.position_id,
            "order_id": executed.order_id,
            "side": side,
            "quantity": quantity,
            "entry_price": opp.entry_price,
        }

    def check_and_update_positions(self) -> list[dict[str, Any]]:
        """Checa posições abertas e atualiza preços/sinais de exit.

        Returns:
            Lista de posições fechadas
        """
        closed_positions = []

        for position in self._position_manager.open_positions:
            # Simular atualização de preço
            current_price = self._get_simulated_price(position.symbol)
            self._position_manager.update_position_price(position.position_id, current_price)

            # Checar sinais de exit
            exit_signals = self._position_manager.check_exit_signals(position.position_id)

            for signal in exit_signals:
                if signal == "stop_loss":
                    exit_reason = ExitReason.STOP_LOSS
                    exit_price = position.stop_loss or current_price
                elif signal == "take_profit":
                    exit_reason = ExitReason.TAKE_PROFIT
                    exit_price = position.take_profit or current_price
                else:
                    continue

                # Fechar posição
                closed = self._position_manager.close_position(
                    position.position_id,
                    exit_price,
                    exit_reason,
                )

                if closed:
                    # Registrar resultado
                    self._register_trade_result(closed)
                    closed_positions.append(closed.to_dict())

                break  # Uma posição fechada, passar para próxima

        return closed_positions

    def _register_trade_result(self, position) -> None:
        """Registra resultado de um trade e aprende."""
        # Atualizar executor
        self._executor.record_trade_result(position.realized_pnl)

        # Atualizar equity
        self.equity += position.realized_pnl
        self._executor.update_equity(self.equity)
        self._position_manager.equity = self.equity

        # Atualizar métricas
        self._total_pnl += position.realized_pnl
        if self._session:
            self._session.total_pnl += position.realized_pnl

        if position.realized_pnl > 0:
            self._total_wins += 1
            if self._session:
                self._session.trades_won += 1

            # Ganhar XP
            xp_gained = int(abs(position.realized_pnl) * 0.1)  # 1 XP por $10 de lucro
            self._xp_system.add_xp(xp_gained)
            if self._session:
                self._session.xp_gained += xp_gained

            logger.info(
                "WIN: %s | PnL: $%.2f | XP: +%d",
                position.symbol,
                position.realized_pnl,
                xp_gained,
            )
        else:
            self._total_losses += 1
            if self._session:
                self._session.trades_lost += 1

            # Registrar dor
            self._pain_memory.remember_pain(
                symbol=position.symbol,
                setup={
                    "entry_price": position.entry_price,
                    "stop_loss": position.stop_loss,
                },
                outcome="loss",
                loss_amount=abs(position.realized_pnl),
                context=position.thesis,
            )

            logger.warning(
                "LOSS: %s | PnL: -$%.2f | Pain registered",
                position.symbol,
                abs(position.realized_pnl),
            )

        # Salvar estado
        self._save_state()

    def run_one_cycle(self) -> dict[str, Any]:
        """Executa um ciclo completo de trading.

        Ciclo:
        1. Scanear mercado
        2. Avaliar oportunidades
        3. Executar trades aprovados
        4. Gerenciar posições
        5. Retornar resumo

        Returns:
            Resumo do ciclo
        """
        cycle_summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "opportunities_found": 0,
            "trades_executed": 0,
            "positions_closed": 0,
            "total_pnl": round(self._total_pnl, 2),
            "equity": round(self.equity, 2),
        }

        # 1. Scanear mercado
        opportunities = self.scan_market()
        cycle_summary["opportunities_found"] = len(opportunities)

        if self._session:
            self._session.opportunities_scanned += len(opportunities)

        logger.info("Scan found %d opportunities", len(opportunities))

        # 2. Avaliar e executar
        for opp in opportunities:
            decision = self.evaluate_opportunity(opp)

            if self._session:
                self._session.decisions_made.append(decision)

            if decision.get("approved"):
                quantity = decision.get("recommended_quantity", 0)
                result = self.execute_trade(opp, quantity)
                if result:
                    cycle_summary["trades_executed"] += 1

        # 3. Gerenciar posições
        closed = self.check_and_update_positions()
        cycle_summary["positions_closed"] = len(closed)

        return cycle_summary

    def get_status(self) -> dict[str, Any]:
        """Retorna status completo do motor."""
        open_positions = self._position_manager.open_positions
        summary = self._position_manager.get_summary(self.equity)

        return {
            "engine": {
                "equity": round(self.equity, 2),
                "total_trades": self._total_trades,
                "total_wins": self._total_wins,
                "total_losses": self._total_losses,
                "win_rate": round(self._total_wins / max(1, self._total_trades), 3),
                "total_pnl": round(self._total_pnl, 2),
                "xp_level": str(self._xp_system.get_level()),
            },
            "positions": {
                "open": len(open_positions),
                "total_value": round(summary.total_value, 2),
                "unrealized_pnl": round(summary.total_unrealized_pnl, 2),
            },
            "session": self._session.to_dict() if self._session else None,
            "kill_switch": self._executor.is_trading_allowed,
        }


def get_trading_engine(equity: float = 10000.0) -> TradingEngine:
    """Retorna instância singleton do TradingEngine."""
    return TradingEngine(equity=equity)
