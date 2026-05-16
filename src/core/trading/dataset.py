"""SFT dataset builder — creates training data from trade signals and outcomes."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SFTExample:
    """A single supervised fine-tuning example."""

    instruction: str
    context: str
    response: str
    reward: float
    source: str
    timestamp: str


class DatasetBuilder:
    """Builds SFT datasets from trade history for LoRA fine-tuning.

    Converts trade outcomes into instruction-response pairs suitable
    for supervised fine-tuning of the CEO decision model.
    """

    def __init__(self, output_dir: str = "data/sft_datasets"):
        self.output_dir = output_dir
        self._examples: list[SFTExample] = []

    def add_from_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        qty: float,
        verdict: float,
        confidence: float,
        expert_signals: dict[str, float],
        pnl: float,
        reward: float,
        reason: str = "",
    ) -> SFTExample:
        now = datetime.now(timezone.utc).isoformat()

        signals_str = ", ".join(
            f"{k}={v:.2f}" for k, v in expert_signals.items()
        )

        instruction = (
            f"Analyze {symbol} for a {side} trade. "
            f"Entry price: {entry_price:.2f}, quantity: {qty:.0f}. "
            f"Expert signals: [{signals_str}]."
        )

        context = (
            f"Verdict: {verdict:.2f}/1.0, Confidence: {confidence:.2f}. "
            f"Result: PnL=${pnl:.2f}, Reward: {reward:.3f}."
        )

        if pnl > 0:
            response = (
                f"APPROVE {side.upper()} {qty:.0f} {symbol} at {entry_price:.2f}. "
                f"Reason: {reason or 'positive expected value'}. "
                f"Verdict: {verdict:.2f}."
            )
        else:
            response = (
                f"REJECT {side.upper()} {qty:.0f} {symbol} at {entry_price:.2f}. "
                f"Reason: {reason or 'negative expected value'}. "
                f"Verdict: {verdict:.2f}."
            )

        example = SFTExample(
            instruction=instruction,
            context=context,
            response=response,
            reward=reward,
            source="trade_history",
            timestamp=now,
        )
        self._examples.append(example)
        return example

    def add_manual(
        self,
        instruction: str,
        context: str,
        response: str,
        reward: float = 0.5,
        source: str = "manual",
    ) -> SFTExample:
        now = datetime.now(timezone.utc).isoformat()
        example = SFTExample(
            instruction=instruction,
            context=context,
            response=response,
            reward=reward,
            source=source,
            timestamp=now,
        )
        self._examples.append(example)
        return example

    def get_examples(self) -> list[SFTExample]:
        return list(self._examples)

    def get_positive_examples(self) -> list[SFTExample]:
        return [e for e in self._examples if e.reward > 0]

    def get_negative_examples(self) -> list[SFTExample]:
        return [e for e in self._examples if e.reward <= 0]

    @property
    def count(self) -> int:
        return len(self._examples)

    def to_jsonl(self, filepath: str | None = None) -> str:
        if filepath is None:
            os.makedirs(self.output_dir, exist_ok=True)
            filepath = os.path.join(
                self.output_dir,
                f"sft_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl",
            )

        with open(filepath, "w", encoding="utf-8") as f:
            for ex in self._examples:
                row = {
                    "instruction": ex.instruction,
                    "context": ex.context,
                    "response": ex.response,
                    "reward": ex.reward,
                    "source": ex.source,
                    "timestamp": ex.timestamp,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        logger.info("Wrote %d examples to %s", len(self._examples), filepath)
        return filepath

    def clear(self) -> None:
        self._examples.clear()
