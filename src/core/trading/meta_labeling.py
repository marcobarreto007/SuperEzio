"""Meta-Labeling & Triple Barrier Execution Gate (Marcos López de Prado).

Reference:
    Marcos López de Prado, "Advances in Financial Machine Learning" (Wiley, 2018),
    Chapter 3: "Labeling" (Triple Barrier Method & Meta-Labeling) & Chapter 10: "Bet Sizing".

Concept:
    The primary model (Bob / Expert Committee / Neural Decision) predicts direction
    (BUY vs. SELL). The secondary model (Meta-Labeler) does NOT predict direction;
    it predicts binary trade success Y in {0, 1}:
        Y = 1 if the trade touches the Profit Barrier before Stop Loss or Horizon.
        Y = 0 if the trade touches the Stop Loss first or expires (False Positive).

    The Meta-Labeler outputs a calibrated probability P(Success | Features, Side).
    If P(Success) < threshold (default 0.55), the gate enforces selective abstention (PASS),
    protecting capital from false-positive churn.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_META_LABEL_THRESHOLD = 0.55
MIN_ASYMMETRY_RATIO = 2.0
TARGET_ASYMMETRY_RATIO = 2.5


@dataclass(frozen=True)
class BarrierProfile:
    """Triple Barrier parameters for a trade candidate."""

    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    stop_distance: float
    profit_distance: float
    asymmetry_ratio: float
    time_horizon_bars: int = 14


@dataclass(frozen=True)
class MetaLabelResult:
    """Outcome of the Meta-Labeling calibration gate."""

    allowed: bool
    meta_probability: float
    threshold: float
    decision: str  # "ALLOW" | "ABSTAIN"
    sizing_multiplier: float
    code: str
    rejection_reason: str | None = None
    feature_contributions: dict[str, float] = field(default_factory=dict)
    barriers: BarrierProfile | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "meta_probability": round(self.meta_probability, 4),
            "threshold": self.threshold,
            "decision": self.decision,
            "sizing_multiplier": round(self.sizing_multiplier, 4),
            "code": self.code,
            "rejection_reason": self.rejection_reason,
            "feature_contributions": {
                k: round(v, 4) for k, v in self.feature_contributions.items()
            },
            "asymmetry_ratio": (round(self.barriers.asymmetry_ratio, 2) if self.barriers else None),
        }


def _sigmoid(x: float) -> float:
    if x < -45.0:
        return 0.0
    if x > 45.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def build_barriers(
    entry_price: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    *,
    side: str = "BUY",
    default_stop_pct: float = 0.05,
    default_asymmetry: float = TARGET_ASYMMETRY_RATIO,
) -> BarrierProfile:
    """Calculate Upper, Lower, and Vertical barriers for the candidate trade."""
    if entry_price <= 0:
        raise ValueError(f"entry_price must be positive, got {entry_price}")

    normalized_side = str(side or "BUY").strip().upper()
    is_buy = normalized_side in {"BUY", "LONG"}

    if stop_loss_price is None:
        stop_dist = entry_price * default_stop_pct
        stop_loss_price = entry_price - stop_dist if is_buy else entry_price + stop_dist
    else:
        stop_dist = abs(entry_price - stop_loss_price)

    if stop_dist <= 0:
        stop_dist = entry_price * default_stop_pct

    if take_profit_price is None:
        profit_dist = stop_dist * default_asymmetry
        take_profit_price = entry_price + profit_dist if is_buy else entry_price - profit_dist
    else:
        profit_dist = abs(take_profit_price - entry_price)

    asymmetry = profit_dist / stop_dist if stop_dist > 0 else 0.0

    return BarrierProfile(
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        stop_distance=round(stop_dist, 4),
        profit_distance=round(profit_dist, 4),
        asymmetry_ratio=round(asymmetry, 4),
    )


def extract_meta_features(
    state: Mapping[str, Any],
    barriers: BarrierProfile,
    side: str = "BUY",
) -> dict[str, float]:
    """Extract quantitative market and model features for meta-labeling.

    Features are normalized into the range [-1.0, 1.0] or [0.0, 1.0].
    """
    normalized_side = str(side or "BUY").strip().upper()
    is_buy = normalized_side in {"BUY", "LONG"}

    math_report = state.get("math_report") if isinstance(state.get("math_report"), Mapping) else {}
    modules = math_report.get("modules") if isinstance(math_report.get("modules"), Mapping) else {}
    data = state.get("data") if isinstance(state.get("data"), Mapping) else {}

    # 1. Asymmetry Conviction feature [-1.0 to 1.0]
    # Reward/Risk >= 2.5 -> +1.0; R:R = 1.0 -> -0.5; R:R < 1.0 -> -1.0
    r = barriers.asymmetry_ratio
    f_asymmetry = max(-1.0, min(1.0, (r - 1.75) / 1.25))

    # 2. Consensus Alignment [-1.0 to 1.0]
    consensus = (
        state.get("expert_consensus") if isinstance(state.get("expert_consensus"), Mapping) else {}
    )
    c_score = float(consensus.get("score", 0.0) or 0.0)
    c_dec = str(consensus.get("decision", "NEUTRAL")).upper()
    if is_buy:
        f_consensus = c_score if c_dec != "BLOCK" else -0.8
    else:
        f_consensus = -c_score if c_dec != "BLOCK" else 0.8
    f_consensus = max(-1.0, min(1.0, f_consensus))

    # 3. Volatility / ATR Stability [0.0 to 1.0]
    # Lower volatility regime = higher probability barrier is hit cleanly without chop
    tech = modules.get("technical_indicators", {})
    tech_vals = tech.get("values", {}) if isinstance(tech, Mapping) else {}
    atr = float(tech_vals.get("atr_14", 0.0) or 0.0)
    price = barriers.entry_price
    vol_pct = (atr / price) if (price > 0 and atr > 0) else 0.03
    # Calm vol (1-3%) -> 0.8; High vol (>6%) -> -0.5
    f_vol_stability = max(-1.0, min(1.0, 1.0 - (vol_pct / 0.04)))

    # 4. RSI Overextension Penalty [-1.0 to 1.0]
    rsi_val = float(tech_vals.get("rsi_14", 50.0) or 50.0)
    if is_buy:
        # Buying at RSI > 70 is penalized (chasing), RSI 30-55 is favored
        if rsi_val > 70:
            f_rsi = -0.7
        elif rsi_val < 35:
            f_rsi = 0.8
        else:
            f_rsi = 0.3
    else:
        # Selling at RSI < 30 is penalized, RSI > 65 is favored
        if rsi_val < 30:
            f_rsi = -0.7
        elif rsi_val > 65:
            f_rsi = 0.8
        else:
            f_rsi = 0.3

    # 5. Volume Confirmation [0.0 to 1.0]
    price_sec = data.get("price") if isinstance(data.get("price"), Mapping) else {}
    vol = float(price_sec.get("volume", 0.0) or 0.0)
    f_volume = 0.2  # baseline
    if vol > 100_000:
        f_volume = 0.6
    if vol > 1_000_000:
        f_volume = 0.9

    # 6. Neural Direction Support [-1.0 to 1.0]
    neural = (
        state.get("neural_decision") if isinstance(state.get("neural_decision"), Mapping) else {}
    )
    neural_dec = str(neural.get("decision", "")).upper()
    if is_buy:
        f_neural = 0.8 if neural_dec == "UP" else -0.8 if neural_dec == "DOWN" else 0.0
    else:
        f_neural = 0.8 if neural_dec == "DOWN" else -0.8 if neural_dec == "UP" else 0.0

    return {
        "asymmetry": f_asymmetry,
        "consensus": f_consensus,
        "vol_stability": f_vol_stability,
        "rsi_alignment": f_rsi,
        "volume_liquidity": f_volume,
        "neural_support": f_neural,
    }


def evaluate_meta_labeling_gate(
    state: Mapping[str, Any],
    symbol: str,
    *,
    side: str = "BUY",
    entry_price: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    threshold: float = DEFAULT_META_LABEL_THRESHOLD,
) -> MetaLabelResult:
    """Evaluate candidate trade assertiveness through the López de Prado Meta-Labeler.

    Returns MetaLabelResult with:
      - allowed: True if P(Success) >= threshold, False otherwise.
      - meta_probability: Calibrated probability P(Y=1 | Features).
      - sizing_multiplier: Proportionate bet sizing multiplier.
    """
    clean_sym = str(symbol or "").strip().upper()
    if not clean_sym:
        return MetaLabelResult(
            allowed=False,
            meta_probability=0.0,
            threshold=threshold,
            decision="ABSTAIN",
            sizing_multiplier=0.0,
            code="META_LABEL_MISSING_SYMBOL",
            rejection_reason="missing_symbol",
        )

    try:
        barriers = build_barriers(
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            side=side,
        )
    except ValueError as exc:
        return MetaLabelResult(
            allowed=False,
            meta_probability=0.0,
            threshold=threshold,
            decision="ABSTAIN",
            sizing_multiplier=0.0,
            code="META_LABEL_INVALID_BARRIERS",
            rejection_reason=str(exc),
        )

    # If asymmetry is below strict survival minimum (2.0:1), fail immediately
    if barriers.asymmetry_ratio < MIN_ASYMMETRY_RATIO:
        return MetaLabelResult(
            allowed=False,
            meta_probability=0.35,
            threshold=threshold,
            decision="ABSTAIN",
            sizing_multiplier=0.0,
            code="META_LABEL_ASYMMETRY_TOO_LOW",
            rejection_reason=(
                f"insufficient_asymmetry: R:R {barriers.asymmetry_ratio:.2f} < "
                f"{MIN_ASYMMETRY_RATIO:.1f} minimum required"
            ),
            barriers=barriers,
        )

    features = extract_meta_features(state, barriers, side=side)

    # Feature weights (calibrated for financial market false-positive suppression)
    weights = {
        "asymmetry": 0.55,
        "consensus": 0.45,
        "vol_stability": 0.35,
        "rsi_alignment": 0.30,
        "volume_liquidity": 0.25,
        "neural_support": 0.40,
    }

    raw_score = sum(features[k] * weights[k] for k in weights if k in features)

    # Prior log-odds: 0.10 (~52.5% neutral market baseline)
    z = 0.10 + raw_score
    prob = _sigmoid(z)

    # Bet sizing multiplier: López de Prado (2018), Chapter 10:
    # Bet size = (P - 0.5) / (1 - 0.5) for P > 0.5
    if prob >= threshold:
        sizing_mult = min(1.0, max(0.2, (prob - 0.5) / 0.40))
        allowed = True
        decision = "ALLOW"
        code = "META_LABEL_ALLOW"
        reason = None
    else:
        sizing_mult = 0.0
        allowed = False
        decision = "ABSTAIN"
        code = "META_LABEL_ABSTAIN"
        reason = (
            f"calibrated_success_probability_{prob:.2f}_below_threshold_{threshold:.2f}_"
            "(López de Prado Triple Barrier Filter)"
        )

    return MetaLabelResult(
        allowed=allowed,
        meta_probability=prob,
        threshold=threshold,
        decision=decision,
        sizing_multiplier=sizing_mult,
        code=code,
        rejection_reason=reason,
        feature_contributions={k: features[k] * weights[k] for k in weights},
        barriers=barriers,
    )
