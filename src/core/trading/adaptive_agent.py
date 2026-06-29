"""Adaptive Agent Bridge — connects Bob's XP, Pain, Auto-Calibration, and RL.

This module is the "spinal cord" between:
- XP System (experience points from trades)
- Bob's Body (pain from sick organs)
- Auto-Calibrator (dynamic trading parameters)
- RL Loop (Q-learning from trade outcomes)

All four feed into calibrated parameters that adjust Bob's decision thresholds
in real-time before he answers each request.
"""

from __future__ import annotations

import numpy as np
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
        "rl_best_action": None,
    }

    # ── XP System ──
    try:
        from core.trading.xp_system import get_xp_system

        xp = get_xp_system()
        config["xp_total"] = getattr(xp, "total_xp", 0)
        config["xp_level"] = getattr(xp, "level_name", "Novice")

        # Higher XP → slightly lower confidence threshold (expertise = confidence)
        xp_bonus = min(0.10, config["xp_total"] / 5000)
        config["buy_confidence_threshold"] -= int(xp_bonus * 100)
    except Exception:
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
    except Exception:
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
        except Exception:
            pass

    # ── Neural RL (policy gradient, replaces tabular Q-learning) ──
    try:
        from core.trading.neural_rl import get_neural_policy

        policy = get_neural_policy()
        rl_state = {
            "confidence": "confidence_high"
            if config["buy_confidence_threshold"] < 80
            else "confidence_medium",
            "market": "market_sideways",
            "pain_level": config["pain_level"],
            "xp_level": min(100, config["xp_total"] // 10),
            "streak": "win_streak",
            "time": "morning",
        }
        best_action, prob = policy.get_best_action(rl_state)
        config["rl_best_action"] = best_action
        config["rl_confidence"] = round(prob, 3)
        config["rl_stats"] = policy.get_stats()
    except Exception:
        pass

    # Clamp safety bounds
    config["buy_confidence_threshold"] = max(50, min(100, config["buy_confidence_threshold"]))
    config["max_position_pct"] = max(0.0, min(0.50, config["max_position_pct"]))
    config["stop_loss_pct"] = max(0.05, min(0.50, config["stop_loss_pct"]))

    return config


def render_adaptive_context(config: dict[str, Any]) -> str:
    """Render calibrated parameters as text for Bob's system prompt."""
    lines = [
        "=== ADAPTIVE TRADING PARAMETERS (XP + Pain + Neural RL calibrated) ===",
        f"XP Level: {config.get('xp_level', '?')} ({config.get('xp_total', 0)} pts)",
        f"Pain: {config.get('pain_level', 0)}/100 [{config.get('pain_mode', 'normal')}]",
        f"Buy Confidence Threshold: {config.get('buy_confidence_threshold', 75)}%",
        f"Max Position: {config.get('max_position_pct', 0.25):.0%} of capital",
        f"Stop Loss: {config.get('stop_loss_pct', 0.15):.0%}",
    ]
    if config.get("rl_best_action"):
        rl_stats = config.get("rl_stats", {})
        lines.append(
            f"Neural RL: {config['rl_best_action']} "
            f"(p={config.get('rl_confidence', 0):.2f}, "
            f"{rl_stats.get('episodes', 0)} eps, "
            f"avg_r={rl_stats.get('avg_reward', 0):.3f})"
        )
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
    except Exception:
        pass

    if ticker_returns:
        try:
            from core.math.portfolio import portfolio_snapshot_for_bob

            return portfolio_snapshot_for_bob(ticker_returns, capital, numbers)
        except Exception:
            pass

    # Fallback: just structured numbers
    try:
        from core.math.portfolio import structured_numbers_context

        return structured_numbers_context(numbers)
    except Exception:
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
    """Record a completed trade for XP, Auto-Calibration, and RL learning.

    Called after a paper trade closes (post_trade_review or paper_journal).
    """
    # XP
    try:
        from core.trading.xp_system import get_xp_system

        xp = get_xp_system()
        xp_gain = 10 if pnl > 0 else -5
        # Pain scaling: bigger losses hurt more
        if pnl < -100:
            xp_gain = -20
        if pnl < -500:
            xp_gain = -50
        getattr(xp, "add_xp", lambda x: None)(xp_gain)
    except Exception:
        pass

    # Auto-Calibration
    try:
        from core.trading.auto_calibration import AutoCalibrator

        cal = AutoCalibrator()
        # Update win_rate signal
        cal.update_parameter("last_trade_pnl", pnl)
        cal.update_parameter("last_trade_result", "win" if pnl > 0 else "loss")
    except Exception:
        pass

    # Neural RL (policy gradient update)
    try:
        from core.trading.neural_rl import get_neural_policy

        policy = get_neural_policy()
        rl_state = {
            "confidence": "confidence_high" if verdict_confidence > 75 else "confidence_medium",
            "market": "market_sideways",
            "pain_level": 50,
            "xp_level": 10,
            "streak": "win_streak" if pnl > 0 else "lose_streak",
            "time": "morning",
        }
        # Reward = PnL as fraction of position value, clipped
        position_value = max(abs(entry * qty), 1.0)
        reward = np.clip(pnl / position_value, -1.0, 1.0)
        policy.update(rl_state, action, float(reward))
        policy.save()
    except Exception:
        pass
