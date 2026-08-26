"""Adaptive Agent Bridge — connects Bob's XP, Pain, Auto-Calibration, and RL.

This module is the "spinal cord" between:
- XP System (experience points from trades)
- Bob's Body (pain from sick organs)
- conservative runtime limits
- OutcomeLearningEngine (durable proper-score expert weights)

All four feed into calibrated parameters that adjust Bob's decision thresholds
in real-time before he answers each request.
"""

from __future__ import annotations

from typing import Any


def get_adaptive_config() -> dict[str, Any]:
    """Returns calibrated trading parameters adjusted by XP + Pain.

    Called by the agent node before Bob's prompt is built.
    Injects calibrated thresholds into the agent's decision context.
    """
    config = {
        "buy_confidence_threshold": 75,
        "max_position_pct": 0.25,
        "stop_loss_pct": 0.15,
        "take_profit_ratio": 2.0,
        "xp_level": "Novice",
        "xp_total": 0,
        "pain_level": 0,
        "pain_mode": "normal",
        "learning_status": "baseline_only",
        "expert_weights": {},
    }

    # ── XP System ──
    try:
        from core.trading.xp_system import get_xp_system

        xp = get_xp_system()
        config["xp_total"] = getattr(xp, "total_xp", 0)
        config["xp_level"] = getattr(xp, "level_name", "Novice")

        # XP é apenas descritivo: fronteira deliberada de melhor esforço —
        # gamificação nunca pode afrouxar um gate de risco nem derrubar a config.
    except Exception:  # noqa: BLE001, S110
        pass

    # ── Pain System (DOMINATES — pain overrides everything) ──
    try:
        from core.bob_consciousness.body import get_bobs_body

        body = get_bobs_body()
        scan = body.full_body_scan()
        config["pain_level"] = scan.get("overall_pain", 0)

        # MAN_AT_WORK → ZERO trading
        if body.is_man_at_work():
            config["pain_mode"] = "man_at_work"
            config["max_position_pct"] = 0.0
            config["buy_confidence_threshold"] = 100
        elif scan.get("critical_count", 0) > 0:
            config["pain_mode"] = "critical"
            config["buy_confidence_threshold"] = 90
            config["max_position_pct"] = 0.05
            config["stop_loss_pct"] = 0.05
        elif config["pain_level"] >= 75:
            config["pain_mode"] = "severe"
            config["buy_confidence_threshold"] = 85
            config["max_position_pct"] = 0.10
        elif config["pain_level"] >= 50:
            config["pain_mode"] = "elevated"
            config["buy_confidence_threshold"] = 80
            config["max_position_pct"] = 0.15
        # Fronteira deliberada de melhor esforço: se a leitura do corpo falhar,
        # segue com os padrões — dor indisponível não pode derrubar o runtime.
    except Exception:  # noqa: BLE001, S110
        pass

    # ── Auto-Calibration (refines only — never overrides pain) ──
    if config["pain_mode"] not in ("critical", "man_at_work"):
        try:
            from core.trading.auto_calibration import AutoCalibrator

            cal = AutoCalibrator()
            cal_config = cal.get_current_config()
            if cal_config:
                cal_threshold = cal_config.get("BUY_CONFIDENCE_THRESHOLD", 75)
                cal_position = cal_config.get("MAX_POSITION_PCT", 0.25)
                cal_stop = cal_config.get("STOP_LOSS_PCT", 0.15)
                config["buy_confidence_threshold"] = max(
                    config["buy_confidence_threshold"], cal_threshold
                )
                config["max_position_pct"] = min(config["max_position_pct"], cal_position)
                config["stop_loss_pct"] = max(config["stop_loss_pct"], cal_stop)
            # Auto-calibração refina apenas: fronteira deliberada de melhor esforço —
            # falha aqui preserva a config atual e nunca sobrescreve a dor.
        except Exception:  # noqa: BLE001, S110
            pass

    # ── Durable outcome learning (weights only, never an order action) ──
    try:
        from core.trading.outcome_learning import (
            DEFAULT_OUTCOME_DB,
            get_effective_expert_weights,
        )

        config["expert_weights"] = get_effective_expert_weights()
        config["learning_status"] = (
            "durable_outcomes_available" if DEFAULT_OUTCOME_DB.exists() else "baseline_only"
        )
        config["learning_method"] = "directional_multiclass_brier_skill_with_shrinkage"
        # Aprendizado durável é opcional (pesos apenas): fronteira deliberada de
        # melhor esforço — falha mantém o baseline e nunca vira ordem.
    except Exception:  # noqa: BLE001, S110
        pass

    # Clamp safety bounds
    config["buy_confidence_threshold"] = max(50, min(100, config["buy_confidence_threshold"]))
    config["max_position_pct"] = max(0.0, min(0.50, config["max_position_pct"]))
    config["stop_loss_pct"] = max(0.05, min(0.50, config["stop_loss_pct"]))

    return config


def render_adaptive_context(config: dict[str, Any]) -> str:
    """Render calibrated parameters as text for Bob's system prompt."""
    lines = [
        "=== ADAPTIVE TRADING PARAMETERS (safety + durable outcomes) ===",
        f"XP Level: {config.get('xp_level', '?')} ({config.get('xp_total', 0)} pts)",
        f"Pain: {config.get('pain_level', 0)}/100 [{config.get('pain_mode', 'normal')}]",
        f"Buy Confidence Threshold: {config.get('buy_confidence_threshold', 75)}%",
        f"Max Position: {config.get('max_position_pct', 0.25):.0%} of capital",
        f"Stop Loss: {config.get('stop_loss_pct', 0.15):.0%}",
    ]
    lines.append(
        f"Outcome learning: {config.get('learning_status', 'unknown')} "
        f"[{config.get('learning_method', 'static_priors')}]"
    )
    if config.get("expert_weights"):
        lines.append(f"Expert reliability weights: {config['expert_weights']}")
    return "\n".join(lines)


def inject_portfolio_context(state: dict[str, Any], capital: float = 10000.0) -> str:
    """Build portfolio allocation + structured numbers for Bob's prompt."""
    math_report = state.get("math_report", {})
    numbers = math_report.get("numbers", {}) or math_report.get("summary", {})

    # Try to get ticker returns from historical cache
    ticker_returns = {}
    try:
        ticker = state.get("ticker", "")
        if ticker:
            from data.data_hub import hub

            candles_resp = hub.get_candles(ticker, timeframe="6M")
            candles = candles_resp.get("candles", [])
            if len(candles) >= 10:
                closes = [c["close"] for c in candles if c.get("close")]
                returns_list = [
                    (closes[i] - closes[i - 1]) / closes[i - 1]
                    for i in range(1, len(closes))
                    if closes[i - 1] > 0
                ]
                if returns_list:
                    ticker_returns[ticker] = returns_list
        # Cache histórico é aprimoramento opcional: fronteira deliberada de melhor
        # esforço — falha cai no fallback de números estruturados.
    except Exception:  # noqa: BLE001, S110
        pass

    if ticker_returns:
        try:
            from core.math.portfolio import portfolio_snapshot_for_bob

            return portfolio_snapshot_for_bob(ticker_returns, capital, numbers)
            # Snapshot é aprimoramento opcional: fronteira deliberada de melhor
            # esforço — falha cai no fallback de números estruturados.
        except Exception:  # noqa: BLE001, S110
            pass

    # Fallback: just structured numbers
    try:
        from core.math.portfolio import structured_numbers_context

        return structured_numbers_context(numbers)
        # Fallback final: fronteira deliberada de melhor esforço — se nem os
        # números estruturados renderizarem, devolve contexto vazio.
    except Exception:  # noqa: BLE001
        return ""


def record_trade_outcome(
    ticker: str,
    action: str,
    entry: float,
    exit_price: float,
    qty: int,
    pnl: float,
    verdict_confidence: float = 0.0,
) -> None:
    """Reject the legacy outcome API because it lacks immutable provenance."""
    del ticker, action, entry, exit_price, qty, pnl, verdict_confidence
    raise RuntimeError(
        "legacy record_trade_outcome lacks trade_id, timestamps, risk and ex-ante "
        "forecasts; close the journal trade and let FeedbackLoop project it into "
        "OutcomeLearningEngine"
    )
