"""Live Trading Engine - Bob operando com dados reais e IBKR.

Conecta Bob ao mundo real:
- Dados de mercado reais (Yahoo/IBKR)
- Execução real via IBKR paper trading
- Aprendizado real com cada trade

Bob agora vive de verdade.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Importar componentes existentes
from .market_hours import get_market_state
from .xp_system import get_xp_system
from .auto_executor import get_auto_executor, ExecutorConfig, ExecutionStatus
from .position_manager import get_position_manager, PositionSide, ExitReason
from .risk_guard import get_risk_guard, RiskGuardResult
from .committee import get_reflection_committee
from .pain_memory import get_pain_memory
from .paper_journal import PaperJournal


class MarketSentiment(Enum):
    """Sentimento de mercado."""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TradingOpportunity:
    """Oportunidade de trading com dados reais."""
    symbol: str
    sentiment: MarketSentiment
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    thesis: str
    expected_move_pct: float
    liquidity_score: float
    market_data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LiveTradingEngine:
    """Motor de trading com dados reais e IBKR.

    Diferenças vs simulado:
    - Usa dados de mercado reais (Yahoo/IBKR)
    - Executa via IBKR paper trading
    - Stop loss/take profit reais
    - PnL real
    """

    def __init__(
        self,
        use_ibkr: bool = True,
        equity: float = 10000.0,
        journal_path: Path | None = None,
        persistence_path: Path | None = None,
    ):
        self.equity = equity
        self._use_ibkr = use_ibkr
        self._journal_path = journal_path or Path("data/paper_journal.jsonl")
        self._persistence_path = persistence_path or Path("data/live_trading_engine_state.json")
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Inicializar componentes
        self._xp_system = get_xp_system()
        self._executor = get_auto_executor(equity=equity)
        self._position_manager = get_position_manager(equity=equity)
        self._risk_guard = get_risk_guard(equity=equity)
        self._committee = get_reflection_committee()
        self._pain_memory = get_pain_memory()
        self._journal = PaperJournal()

        # Market data provider
        self._market_data_provider = None

        # Estado
        self._session_start: str | None = None
        self._last_scan_time: float = 0
        self._scan_interval_seconds: int = 60  # Scan a cada 60s (dados reais)
        self._watchlist: list[str] = ["AAPL", "SPY", "QQQ", "IWM", "TLT", "GLD"]

        # Métricas
        self._total_trades = 0
        self._total_wins = 0
        self._total_losses = 0
        self._total_pnl = 0.0

        # Carregar estado anterior
        self._load_state()

        # Inicializar market data provider
        self._init_market_data()

    def _init_market_data(self) -> None:
        """Inicializa provider de dados de mercado."""
        try:
            from adapters.market.market_data_provider import get_market_data_provider
            self._market_data_provider = get_market_data_provider(prefer_ibkr=self._use_ibkr)
            logger.info("Market data provider initialized (IBKR: %s)", self._use_ibkr)
        except Exception as e:
            logger.warning("Failed to init market data provider: %s", e)

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
                    self.equity = state.get("equity", self.equity)
                    logger.info("State loaded: %d trades, PnL: $%.2f", self._total_trades, self._total_pnl)
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

    def start_session(self) -> dict[str, Any]:
        """Start or resume a live autonomous session."""
        if self._session_start is None:
            self._session_start = datetime.now(timezone.utc).isoformat()
            logger.info("Live trading session started")
        return {
            "started_at": self._session_start,
            "trades_executed": self._total_trades,
            "total_pnl": round(self._total_pnl, 2),
        }

    def end_session(self) -> dict[str, Any] | None:
        """End the current live autonomous session."""
        if self._session_start is None:
            return None
        summary = {
            "started_at": self._session_start,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "trades_executed": self._total_trades,
            "trades_won": self._total_wins,
            "trades_lost": self._total_losses,
            "total_pnl": round(self._total_pnl, 2),
            "win_rate": round(self._total_wins / max(1, self._total_trades), 3),
        }
        self._session_start = None
        self._save_state()
        logger.info("Live trading session ended: %s", summary)
        return summary

    def update_equity_from_broker(self) -> float:
        """Atualiza equity do broker IBKR."""
        if not self._use_ibkr:
            return self.equity

        try:
            from adapters.broker.ibkr_service import get_ibkr_service
            service = get_ibkr_service()
            equity = service.get_account_equity()
            if equity and equity > 0:
                self.equity = equity
                self._executor.update_equity(equity)
                self._position_manager.equity = equity
                self._risk_guard.update_equity(equity)
                logger.info("Equity updated from IBKR: $%.2f", equity)
        except Exception as e:
            logger.warning("Failed to update equity from IBKR: %s", e)

        return self.equity

    def scan_market_real(self) -> list[TradingOpportunity]:
        """Scaneia mercado com dados reais."""
        if not self._market_data_provider:
            logger.error("No market data provider available")
            return []

        opportunities = []
        market_state = get_market_state(cached=False)

        # Só scanear se mercado estiver aberto
        if not market_state["is_open"]:
            logger.debug("Market closed, skipping scan")
            return []

        # Obter dados de todos os ativos
        all_data = self._market_data_provider.get_batch_data(self._watchlist)

        for symbol, data in all_data.items():
            opp = self._analyze_symbol(symbol, data)
            if opp:
                opportunities.append(opp)

        logger.info("Market scan: %d opportunities found (real data)", len(opportunities))
        return opportunities

    def _analyze_symbol(self, symbol: str, data: Any) -> TradingOpportunity | None:
        """Analisa um símbolo com dados reais."""
        last_price = data.last_price
        change_pct = data.change_pct or 0

        # Análise simples baseada em tendência
        if change_pct > 0.5:  # +0.5% ou mais
            sentiment = MarketSentiment.BULLISH
            confidence = min(0.85, 0.5 + abs(change_pct) / 100)
            stop_loss = last_price * 0.98  # 2% SL
            take_profit = last_price * 1.04  # 4% TP
            thesis = f"Forte movimento de alta ({change_pct:+.2f}%), tendência de compra"

        elif change_pct < -0.5:  # -0.5% ou mais
            sentiment = MarketSentiment.BEARISH
            confidence = min(0.85, 0.5 + abs(change_pct) / 100)
            stop_loss = last_price * 1.02  # 2% SL (para short)
            take_profit = last_price * 0.96  # 4% TP (para short)
            thesis = f"Forte movimento de baixa ({change_pct:+.2f}%), tendência de venda"

        else:
            return None  # Neutro, pular

        # Checar pain memory
        pain_risk = self._pain_memory.check_setup_risk({
            "symbol": symbol,
            "entry_price": last_price,
            "stop_loss": stop_loss,
        })

        if pain_risk.get("level") == "SEVERE":
            logger.info("Skipping %s due to pain memory", symbol)
            return None

        # Liquidez score baseada em volume
        avg_vol = data.avg_daily_volume or 1_000_000
        liquidity_score = min(1.0, avg_vol / 10_000_000)  # Normaliza para $10M

        return TradingOpportunity(
            symbol=symbol,
            sentiment=sentiment,
            confidence=confidence * (0.8 if pain_risk.get("level") == "HIGH" else 1.0),
            entry_price=last_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            thesis=thesis,
            expected_move_pct=abs(take_profit - last_price) / last_price,
            liquidity_score=liquidity_score,
            market_data=data.to_dict(),
        )

    def evaluate_opportunity_real(self, opp: TradingOpportunity) -> dict[str, Any]:
        """Avalia oportunidade com gates reais."""
        decision = {
            "opportunity": {
                "symbol": opp.symbol,
                "sentiment": opp.sentiment.value,
                "confidence": round(opp.confidence, 3),
                "entry_price": round(opp.entry_price, 2),
                "market_data": opp.market_data,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "approved": False,
            "rejection_reason": None,
        }

        # Risk guard
        side = "buy" if opp.sentiment == MarketSentiment.BULLISH else "sell"
        risk_result = self._risk_guard.check_trade(
            symbol=opp.symbol,
            side=side,
            quantity=10,  # Placeholder
            entry_price=opp.entry_price,
            stop_loss=opp.stop_loss,
            market_data={"avg_daily_volume": opp.market_data.get("avg_daily_volume", 1_000_000)},
        )

        decision["risk_guard"] = risk_result.to_dict()
        if not risk_result.approved:
            decision["rejection_reason"] = "risk_guard"
            return decision

        # Committee
        setup = {
            "ticker": opp.symbol,
            "side": side,
            "entry_price": opp.entry_price,
            "stop_loss": opp.stop_loss,
            "take_profit": opp.take_profit,
            "thesis": opp.thesis,
            "confidence": opp.confidence,
            "market_change_pct": opp.market_data.get("change_pct", 0),
        }
        committee_decision = self._committee.deliberate(setup)
        decision["committee"] = {
            "consensus": committee_decision.consensus.value,
            "is_approved": committee_decision.is_approved,
        }

        if not committee_decision.is_approved:
            decision["rejection_reason"] = "committee"
            return decision

        # Calcular quantidade
        risk_per_share = abs(opp.entry_price - opp.stop_loss)
        max_risk = self.equity * 0.02
        shares_by_risk = int(max_risk / risk_per_share)
        max_position = self.equity * 0.10
        shares_by_position = int(max_position / opp.entry_price)
        quantity = min(shares_by_risk, shares_by_position)

        decision["approved"] = True
        decision["recommended_quantity"] = quantity

        logger.info(
            "Opportunity approved: %s %s %d shares @ $%.2f (conf: %.0f%%)",
            side.upper(),
            opp.symbol,
            quantity,
            opp.entry_price,
            opp.confidence * 100,
        )

        return decision

    def execute_trade_real(self, opp: TradingOpportunity, quantity: int) -> dict[str, Any] | None:
        """Executa trade real via IBKR."""
        side = "buy" if opp.sentiment == MarketSentiment.BULLISH else "sell"
        position_side = PositionSide.LONG if side == "buy" else PositionSide.SHORT

        # Preparar ordem
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

        if request.status != ExecutionStatus.APPROVED:
            logger.warning("Trade rejected by executor: %s", request.rejection_reason)
            return None

        # Executar via IBKR
        if self._use_ibkr:
            try:
                from core.trading.broker import Order, OrderSide, OrderStatus, OrderType
                from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter

                adapter = InteractiveBrokersAdapter()
                limit_price = round(float(opp.entry_price), 4)
                order = Order(
                    id=f"live-{int(time.time())}",
                    symbol=opp.symbol,
                    side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    qty=quantity,
                    status=OrderStatus.PENDING,
                    limit_price=limit_price,
                )

                result = adapter.submit_order(order)

                if result.status.value == "rejected":
                    logger.error("IBKR rejected order: %s", opp.symbol)
                    return None

                logger.info("IBKR Order submitted: %s -> %s", opp.symbol, result.id)

            except Exception as e:
                logger.error("IBKR execution failed: %s", e)
                return None

        # Criar posição local
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

        # Atualizar contadores
        self._total_trades += 1

        # Registrar no journal
        self._journal.add_trade({
            "trade_id": position.position_id,
            "symbol": opp.symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": opp.entry_price,
            "stop_loss": opp.stop_loss,
            "take_profit": opp.take_profit,
            "thesis": opp.thesis,
            "verdict_at_entry": f"Confidence {opp.confidence*100:.0f}%",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_data": opp.market_data,
        })

        logger.info(
            "TRADE EXECUTED (REAL): %s %s %d shares @ $%.2f | ID: %s",
            side.upper(),
            opp.symbol,
            quantity,
            opp.entry_price,
            position.position_id,
        )

        return {
            "position_id": position.position_id,
            "symbol": opp.symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": opp.entry_price,
        }

    def check_positions_real(self) -> list[dict[str, Any]]:
        """Checa posições com dados reais e fecha se necessário."""
        closed_positions = []

        for position in self._position_manager.open_positions:
            # Atualizar preço com dados reais
            if self._market_data_provider:
                data = self._market_data_provider.get_data(position.symbol)
                if data:
                    self._position_manager.update_position_price(position.position_id, data.last_price)

            # Checar sinais de exit
            exit_signals = self._position_manager.check_exit_signals(position.position_id)

            for signal in exit_signals:
                if signal == "stop_loss":
                    exit_reason = ExitReason.STOP_LOSS
                    exit_price = position.stop_loss or position.current_price
                elif signal == "take_profit":
                    exit_reason = ExitReason.TAKE_PROFIT
                    exit_price = position.take_profit or position.current_price
                else:
                    continue

                # Fechar posição
                closed = self._position_manager.close_position(
                    position.position_id,
                    exit_price,
                    exit_reason,
                )

                if closed:
                    self._register_result(closed)

                    # Fechar ordem no IBKR se necessário
                    if self._use_ibkr:
                        self._close_ibkr_position(position, exit_price)

                    closed_positions.append(closed.to_dict())

                break

        return closed_positions

    def _close_ibkr_position(self, position, exit_price: float) -> None:
        """Fecha posição no IBKR."""
        try:
            from adapters.broker.ibkr_adapter import InteractiveBrokersAdapter
            from core.trading.broker import Order, OrderSide, OrderStatus, OrderType

            adapter = InteractiveBrokersAdapter()
            side = "sell" if position.side.value == "long" else "buy"
            limit_price = round(float(exit_price), 4)

            order = Order(
                id=f"close-{position.position_id}",
                symbol=position.symbol,
                side=OrderSide.SELL if side == "sell" else OrderSide.BUY,
                order_type=OrderType.LIMIT,
                qty=position.quantity,
                status=OrderStatus.PENDING,
                limit_price=limit_price,
            )

            result = adapter.submit_order(order)
            logger.info("IBKR Close order: %s -> %s", position.symbol, result.id)

        except Exception as e:
            logger.error("IBKR close failed: %s", e)

    def _register_result(self, position) -> None:
        """Registra resultado e aprende."""
        self._executor.record_trade_result(position.realized_pnl)
        self.equity += position.realized_pnl
        self._executor.update_equity(self.equity)
        self._position_manager.equity = self.equity
        self._total_pnl += position.realized_pnl

        if position.realized_pnl > 0:
            self._total_wins += 1
            xp = int(abs(position.realized_pnl) * 0.1)
            self._xp_system.add_xp(xp)
            logger.info("WIN: %s +$%.2f | XP +%d", position.symbol, position.realized_pnl, xp)
        else:
            self._total_losses += 1
            self._pain_memory.remember_pain(
                symbol=position.symbol,
                setup={"entry_price": position.entry_price, "stop_loss": position.stop_loss},
                outcome="loss",
                loss_amount=abs(position.realized_pnl),
                context=position.thesis,
            )
            logger.warning("LOSS: %s -$%.2f | Pain registered", position.symbol, abs(position.realized_pnl))

        self._save_state()

    def run_one_cycle_real(self) -> dict[str, Any]:
        """Executa um ciclo real."""
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_open": False,
            "opportunities": 0,
            "trades": 0,
            "closed": 0,
            "equity": round(self.equity, 2),
        }

        market_state = get_market_state(cached=False)
        summary["market_open"] = market_state["is_open"]

        if not market_state["is_open"]:
            logger.debug("Market closed, skipping cycle")
            return summary

        # Atualizar equity do broker
        self.update_equity_from_broker()

        # Scanear
        opportunities = self.scan_market_real()
        summary["opportunities"] = len(opportunities)

        # Avaliar e executar
        for opp in opportunities:
            decision = self.evaluate_opportunity_real(opp)
            if decision.get("approved"):
                qty = decision.get("recommended_quantity", 0)
                if qty > 0:
                    result = self.execute_trade_real(opp, qty)
                    if result:
                        summary["trades"] += 1

        # Gerenciar posições
        closed = self.check_positions_real()
        summary["closed"] = len(closed)

        return summary

    def run_one_cycle(self) -> dict[str, Any]:
        """Compatibility wrapper for AutonomousLoop."""
        summary = self.run_one_cycle_real()
        summary["trades_executed"] = summary.get("trades", 0)
        summary["positions_closed"] = summary.get("closed", 0)
        summary["total_pnl"] = round(self._total_pnl, 2)
        return summary

    def check_and_update_positions(self) -> list[dict[str, Any]]:
        """Compatibility wrapper for AutonomousLoop."""
        return self.check_positions_real()

    def get_status_real(self) -> dict[str, Any]:
        """Status completo."""
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
            "live": self._use_ibkr,
            "market_data": "IBKR" if self._use_ibkr else "Yahoo",
        }

    def get_status(self) -> dict[str, Any]:
        """Compatibility wrapper for AutonomousLoop and cockpit probes."""
        status = self.get_status_real()
        status["session"] = self._session_start is not None
        status["engine"]["mode"] = "live_ibkr" if self._use_ibkr else "live_market_data"
        status["engine"]["session_started_at"] = self._session_start
        return status


def get_live_trading_engine(use_ibkr: bool = True, equity: float = 10000.0) -> LiveTradingEngine:
    """Retorna instância do Live Trading Engine."""
    return LiveTradingEngine(use_ibkr=use_ibkr, equity=equity)
