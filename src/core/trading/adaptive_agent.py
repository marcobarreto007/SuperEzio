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
                config["buy_confidence_threshold"] = max(config["buy_confidence_threshold"], cal_threshold)
                config["max_position_pct"] = min(config["max_position_pct"], cal_position)
                config["stop_loss_pct"] = max(config["stop_loss_pct"], cal_stop)
        except Exception:
            pass
    
    # ── RL Loop ──
    try:
        from core.trading.rl_loop import RLLoop
        rl = RLLoop()
        state = {
            "confidence": "confidence_high" if config["buy_confidence_threshold"] < 80 else "confidence_medium",
            "market": "market_sideways",
            "time": "morning",
            "streak": "win_streak",
        }
        config["rl_best_action"] = rl.choose_action(state)
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
        "=== ADAPTIVE TRADING PARAMETERS (XP + Pain calibrated) ===",
        f"XP Level: {config.get('xp_level', '?')} ({config.get('xp_total', 0)} pts)",
        f"Pain: {config.get('pain_level', 0)}/100 [{config.get('pain_mode', 'normal')}]",
        f"Buy Confidence Threshold: {config.get('buy_confidence_threshold', 75)}%",
        f"Max Position: {config.get('max_position_pct', 0.25):.0%} of capital",
        f"Stop Loss: {config.get('stop_loss_pct', 0.15):.0%}",
    ]
    if config.get("rl_best_action"):
        lines.append(f"RL Suggestion: {config['rl_best_action']}")
    return "\n".join(lines)


def record_trade_outcome(
    ticker: str, action: str, entry: float, exit_price: float,
    qty: int, pnl: float, verdict_confidence: float = 0.0,
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
    
    # RL Loop
    try:
        from core.trading.rl_loop import RLLoop
        rl = RLLoop()
        state = {
            "confidence": "confidence_high" if verdict_confidence > 75 else "confidence_medium",
            "market": "market_sideways",
            "time": "morning",
            "streak": "win_streak" if pnl > 0 else "win_streak",
        }
        rl.record_episode(action, state, pnl / max(abs(entry * qty), 1))
    except Exception:
        pass
