"""Autonomous Loop - Bob 24/7 operando no mercado.

Loop principal que:
- Fica em execucao continua
- Opera quando o mercado esta aberto
- Estuda quando esta fechado
- Aprende com cada resultado
- Nunca desliga

Bob agora e um organismo vivo.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market_hours import get_market_state
from .trading_engine import get_trading_engine
from .trading_engine_live import get_live_trading_engine

logger = logging.getLogger(__name__)


class AutonomousLoop:
    """Loop autônomo 24/7 do Bob.

    Estados:
    - SCANNING: Scaneando oportunidades
    - TRADING: Executando trades
    - MANAGING: Gerenciando posições
    - LEARNING: Analisando resultados
    - RESTING: Mercado fechado, estudando
    """

    def __init__(
        self,
        equity: float = 10000.0,
        scan_interval_seconds: int = 30,
        persistence_path: Path | None = None,
        use_live_engine: bool | None = None,
        use_ibkr: bool = True,
        engine: Any | None = None,
    ):
        self.equity = equity
        self._scan_interval = scan_interval_seconds
        self._persistence_path = persistence_path or Path("data/autonomous_loop_state.json")
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Motor de trading
        if engine is not None:
            self._engine = engine
            self._engine_mode = "injected"
        else:
            if use_live_engine is None:
                use_live_engine = (
                    os.getenv("SUPEREZIO_AUTONOMOUS_ENGINE", "live").lower() != "simulated"
                )
            if use_live_engine:
                self._engine = get_live_trading_engine(use_ibkr=use_ibkr, equity=equity)
                self._engine_mode = "live_ibkr" if use_ibkr else "live_market_data"
            else:
                self._engine = get_trading_engine(equity=equity)
                self._engine_mode = "simulated"

        # Estado
        self._running = False
        self._shutdown_requested = False
        self._cycle_count = 0
        self._start_time: float = 0

        # Estatísticas
        self._stats = {
            "cycles_completed": 0,
            "trades_executed": 0,
            "total_pnl": 0.0,
            "hours_running": 0.0,
        }

        # Setup signal handlers para shutdown gracioso
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, _frame):
        """Handler para sinais de shutdown."""
        logger.info("Shutdown signal received (%s)", signum)
        self._shutdown_requested = True

    async def start(self) -> None:
        """Inicia o loop autônomo."""
        if self._running:
            logger.warning("Loop already running")
            return

        self._running = True
        self._start_time = time.time()
        logger.info("=" * 60)
        logger.info("BOB AUTONOMOUS LOOP STARTED")
        logger.info(
            "Equity: $%.2f | Scan interval: %ds | Engine: %s",
            self.equity,
            self._scan_interval,
            self._engine_mode,
        )
        logger.info("=" * 60)

        try:
            await self._main_loop()
        except Exception as e:
            logger.exception("Fatal error in main loop: %s", e)
        finally:
            await self._shutdown()

    async def _main_loop(self) -> None:
        """Loop principal."""
        while not self._shutdown_requested:
            try:
                # Checar estado do mercado
                market_state = get_market_state(cached=False)
                is_open = market_state["is_open"]
                phase = market_state["phase"]

                logger.debug("Market phase: %s | Open: %s", phase, is_open)

                if is_open and phase == "MARKET_OPEN":
                    # Mercado aberto - operar!
                    await self._trading_cycle()
                elif phase in ["PRE_MARKET", "POST_MARKET"]:
                    # Pré/pós mercado - preparar/analizar
                    await self._preparation_cycle()
                else:
                    # Mercado fechado - descansar e estudar
                    await self._rest_cycle()

                self._cycle_count += 1

                # Atualizar estatísticas a cada 10 ciclos
                if self._cycle_count % 10 == 0:
                    self._update_stats()
                    self._log_status()

                # Pequena pausa
                await asyncio.sleep(5)

            except asyncio.CancelledError:
                logger.info("Loop cancelled")
                break
            except Exception as e:
                logger.error("Error in cycle: %s", e)
                await asyncio.sleep(10)  # Esperar antes de tentar novamente

    async def _trading_cycle(self) -> None:
        """Ciclo de trading ativo."""
        logger.info("🎯 TRADING CYCLE %d", self._cycle_count)

        # Iniciar sessão se não houver
        status = self._engine_status()
        if not status.get("session"):
            self._engine_start_session()

        # Executar ciclo completo
        summary = self._engine_run_one_cycle()

        # Log resultado
        if summary["trades_executed"] > 0 or summary.get("orders_submitted", 0) > 0:
            logger.info(
                "✅ Ordens submetidas: %d | Trades confirmados: %d | Posições fechadas: %d | PnL acumulado: $%.2f",
                summary.get("orders_submitted", 0),
                summary["trades_executed"],
                summary["positions_closed"],
                summary["total_pnl"],
            )
        elif summary["opportunities_found"] > 0:
            logger.debug(
                "Oportunidades: %d | Nenhuma aprovada pelos gates",
                summary["opportunities_found"],
            )

        # Esperar próximo scan
        await asyncio.sleep(self._scan_interval)

    async def _preparation_cycle(self) -> None:
        """Ciclo de preparação (pré/pós market)."""
        logger.debug("📊 Preparation cycle")

        # Atualizar posições (checar stops)
        closed = self._engine_check_positions()

        if closed:
            logger.info("🔒 Posições fechadas fora de mercado: %d", len(closed))

        # Finalizar sessão se pós-market
        market_state = get_market_state(cached=False)
        if market_state["phase"] == "POST_MARKET":
            session = self._engine_end_session()
            if session:
                logger.info(
                    "📋 Session summary: %d trades, $%.2f PnL, %.1f%% win rate",
                    self._session_value(session, "trades_executed", 0),
                    self._session_value(session, "total_pnl", 0.0),
                    self._session_value(session, "win_rate", 0.0) * 100,
                )

        await asyncio.sleep(self._scan_interval * 2)

    async def _rest_cycle(self) -> None:
        """Ciclo de descanso (mercado fechado)."""
        logger.debug("😴 Rest cycle (market closed)")

        study = self._engine_study_closed_market()
        if study and not study.get("skipped"):
            logger.info(
                "Closed-market study: reviewed=%d blocking=%s",
                len(study.get("aged_theses_reviewed") or []),
                (study.get("reconciliation") or {}).get("blocking"),
            )

        # Calcular tempo até próxima abertura
        market_state = get_market_state(cached=False)
        seconds_to_open = market_state.get("time_until_open_seconds", 0)
        hours_to_open = seconds_to_open / 3600

        logger.info("🌙 Market closed. Next open in %.1fh", hours_to_open)

        # Dormir até 1h antes da abertura
        sleep_seconds = (
            min(seconds_to_open - 3600, self._scan_interval * 4) if seconds_to_open > 3600 else 300
        )

        if sleep_seconds > 0:
            logger.info("💤 Sleeping for %.1f minutes", sleep_seconds / 60)
            await asyncio.sleep(sleep_seconds)

    def _update_stats(self) -> None:
        """Atualiza estatísticas."""
        self._stats["cycles_completed"] = self._cycle_count
        self._stats["hours_running"] = (time.time() - self._start_time) / 3600

        status = self._engine_status()
        engine = status.get("engine", {})

        self._stats["trades_executed"] = engine.get("total_trades", 0)
        self._stats["total_pnl"] = engine.get("total_pnl", 0.0)

    def _log_status(self) -> None:
        """Log status atual."""
        status = self._engine_status()
        engine = status.get("engine", {})
        positions = status.get("positions", {})

        logger.info(
            "📊 STATUS | Equity: $%.2f | Trades: %d (%.1f%% win) | PnL: $%.2f | XP: %s | Posições abertas: %d",
            engine.get("equity", self.equity),
            engine.get("total_trades", 0),
            engine.get("win_rate", 0) * 100,
            engine.get("total_pnl", 0.0),
            engine.get("xp_level", "N/A"),
            positions.get("open", 0),
        )

    async def _shutdown(self) -> None:
        """Shutdown gracioso."""
        logger.info("🛑 Shutting down...")

        self._running = False

        # Finalizar sessão
        session = self._engine_end_session()
        if session:
            logger.info(
                "Final session: %d trades, $%.2f PnL",
                self._session_value(session, "trades_executed", 0),
                self._session_value(session, "total_pnl", 0.0),
            )

        # Salvar estado final
        self._save_final_state()

        logger.info("✓ Shutdown complete")

    def _save_final_state(self) -> None:
        """Salva estado final."""
        try:
            status = self._engine_status()
            final_state = {
                "shutdown_time": datetime.now(timezone.utc).isoformat(),
                "stats": self._stats,
                "engine_mode": self._engine_mode,
                "engine": {
                    "equity": status.get("engine", {}).get("equity", self.equity),
                    "total_trades": status.get("engine", {}).get("total_trades", 0),
                    "total_pnl": status.get("engine", {}).get("total_pnl", 0.0),
                },
                "cycles_completed": self._cycle_count,
            }

            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(final_state, f, indent=2)

            logger.info("Final state saved to %s", self._persistence_path)
        except Exception as e:
            logger.warning("Failed to save final state: %s", e)

    def _engine_status(self) -> dict[str, Any]:
        if hasattr(self._engine, "get_status"):
            return self._engine.get_status()
        if hasattr(self._engine, "get_status_real"):
            return self._engine.get_status_real()
        return {}

    def _engine_start_session(self) -> Any:
        if hasattr(self._engine, "start_session"):
            return self._engine.start_session()
        return None

    def _engine_end_session(self) -> Any:
        if hasattr(self._engine, "end_session"):
            return self._engine.end_session()
        return None

    def _engine_run_one_cycle(self) -> dict[str, Any]:
        if hasattr(self._engine, "run_one_cycle"):
            return self._engine.run_one_cycle()
        if hasattr(self._engine, "run_one_cycle_real"):
            summary = self._engine.run_one_cycle_real()
            summary["trades_executed"] = summary.get("trades", 0)
            summary["positions_closed"] = summary.get("closed", 0)
            summary["total_pnl"] = summary.get("total_pnl", 0.0)
            return summary
        return {
            "trades_executed": 0,
            "positions_closed": 0,
            "total_pnl": 0.0,
            "opportunities_found": 0,
        }

    def _engine_check_positions(self) -> list[dict[str, Any]]:
        if hasattr(self._engine, "check_and_update_positions"):
            return self._engine.check_and_update_positions()
        if hasattr(self._engine, "check_positions_real"):
            return self._engine.check_positions_real()
        return []

    def _engine_study_closed_market(self) -> dict[str, Any] | None:
        if hasattr(self._engine, "study_closed_market"):
            return self._engine.study_closed_market()
        return None

    def _session_value(self, session: Any, key: str, default: Any) -> Any:
        if isinstance(session, dict):
            return session.get(key, default)
        return getattr(session, key, default)


async def run_autonomous_loop(
    equity: float = 10000.0,
    scan_interval_seconds: int = 30,
    use_live_engine: bool | None = None,
    use_ibkr: bool = True,
) -> None:
    """Função conveniente para rodar o loop autônomo."""
    loop = AutonomousLoop(
        equity=equity,
        scan_interval_seconds=scan_interval_seconds,
        use_live_engine=use_live_engine,
        use_ibkr=use_ibkr,
    )
    await loop.start()


if __name__ == "__main__":
    # Rodar diretamente para teste
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    asyncio.run(run_autonomous_loop(equity=10000.0, scan_interval_seconds=30))
