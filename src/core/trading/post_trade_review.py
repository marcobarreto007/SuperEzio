"""Post-Trade Review - Análise automática pós-trade.

Bob analisa cada trade fechado automaticamente:
- Compara verdict vs outcome
- Identifica o que deu certo/errado
- Gera lição aprendida
- Atualiza XP
- Registra no pain memory se necessário
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_REVIEW_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "data" / "post_trade_review_log.jsonl"
)


@dataclass
class TradeReview:
    """Análise de um trade fechado."""
    review_id: str
    timestamp: str
    trade_id: str
    ticker: str
    entry_verdict: str  # Veredito original
    outcome: str  # win/loss/breakeven
    pnl_amount: float | None
    pnl_percent: float | None
    thesis_correct: bool | None
    confidence_at_entry: float | None
    verdict_match: bool  # Se verdict previu outcome
    what_went_right: list[str] = field(default_factory=list)
    what_went_wrong: list[str] = field(default_factory=list)
    lesson_learned: str | None = None
    improvements: list[str] = field(default_factory=list)
    severity: str = "low"  # low/medium/high

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "timestamp": self.timestamp,
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "entry_verdict": self.entry_verdict,
            "outcome": self.outcome,
            "pnl_amount": self.pnl_amount,
            "pnl_percent": self.pnl_percent,
            "thesis_correct": self.thesis_correct,
            "confidence_at_entry": self.confidence_at_entry,
            "verdict_match": self.verdict_match,
            "what_went_right": self.what_went_right,
            "what_went_wrong": self.what_went_wrong,
            "lesson_learned": self.lesson_learned,
            "improvements": self.improvements,
            "severity": self.severity,
        }


class PostTradeReviewer:
    """Revisor de trades pós-fechamento."""

    def __init__(
        self,
        log_path: Path | None = None,
    ):
        self._log_path = log_path or DEFAULT_REVIEW_LOG_PATH
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    def _generate_review_id(self) -> str:
        """Gera ID único para review."""
        return f"review_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    def _save_review(self, review: TradeReview) -> None:
        """Salva review no disco (append-only)."""
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(review.to_dict(), ensure_ascii=False) + "\n")

    def _extract_confidence(self, verdict: str) -> float | None:
        """Extrai confiança do veredito."""
        import re
        patterns = [
            r"(?:confidence|confiança|conf)\D{0,10}(\d{1,3})",
            r"(\d{1,3})\s*/\s*100",
            r"(\d{1,3})\s*%",
        ]
        for pattern in patterns:
            match = re.search(pattern, verdict, re.IGNORECASE)
            if match:
                conf = float(match.group(1))
                return min(1.0, max(0.0, conf / 100)) if conf > 1 else conf
        return None

    def review_trade(
        self,
        trade: dict[str, Any],
    ) -> TradeReview:
        """Analisa um trade fechado.

        Args:
            trade: Trade do journal

        Returns:
            Review completo
        """
        review_id = self._generate_review_id()

        # Extrair campos
        trade_id = trade.get("trade_id", "")
        ticker = trade.get("ticker", "")
        entry_verdict = trade.get("verdict_at_entry", "")
        outcome = trade.get("outcome", "")
        pnl = trade.get("pnl_amount")
        pnl_pct = trade.get("pnl_percent")
        thesis_correct = trade.get("thesis_correct")
        exit_reason = trade.get("exit_reason", "")

        # Extrair confiança
        confidence = self._extract_confidence(entry_verdict)

        # Determinar se verdict previu outcome
        verdict_match = False
        if outcome == "win" and confidence and confidence >= 0.7:
            verdict_match = True
        elif outcome == "loss" and confidence and confidence < 0.5:
            verdict_match = True

        # Analisar o que deu certo/errado
        what_went_right = []
        what_went_wrong = []
        improvements = []

        if outcome == "win":
            if thesis_correct:
                what_went_right.append("Tese confirmada pelo mercado")
            if pnl and pnl > 0:
                what_went_right.append(f"Lucro de ${pnl:.2f}")
            if exit_reason == "take_profit":
                what_went_right.append("Exit em target atingido")

            # O que pode ter melhorado
            if pnl_pct and pnl_pct < 2:
                improvements.append("Considerar segurar mais tempo para upside adicional")

        elif outcome == "loss":
            if not thesis_correct:
                what_went_wrong.append("Tese não se confirmou")
            if pnl and pnl < 0:
                what_went_wrong.append(f"Perda de ${abs(pnl):.2f}")
            if exit_reason == "stop_loss":
                what_went_wrong.append("Stop loss acionado")

            # O que pode ter melhorado
            if exit_reason != "stop_loss" and pnl_pct and pnl_pct < -2:
                improvements.append("Usar stop loss para limitar perdas")
            if confidence and confidence < 0.6:
                improvements.append("Evitar trades com baixa confiança")

        # Determinar severidade
        pnl_abs = abs(pnl) if pnl else 0
        if pnl_abs > 500:
            severity = "high"
        elif pnl_abs > 100:
            severity = "medium"
        else:
            severity = "low"

        # Gerar lição
        lesson = self._generate_lesson(
            ticker=ticker,
            outcome=outcome,
            thesis_correct=thesis_correct,
            what_went_right=what_went_right,
            what_went_wrong=what_went_wrong,
        )

        review = TradeReview(
            review_id=review_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            trade_id=trade_id,
            ticker=ticker,
            entry_verdict=entry_verdict[:200],  # Truncar se muito longo
            outcome=outcome,
            pnl_amount=pnl,
            pnl_percent=pnl_pct,
            thesis_correct=thesis_correct,
            confidence_at_entry=confidence,
            verdict_match=verdict_match,
            what_went_right=what_went_right,
            what_went_wrong=what_went_wrong,
            lesson_learned=lesson,
            improvements=improvements,
            severity=severity,
        )

        self._save_review(review)
        logger.info("Review complete: %s %s outcome=%s severity=%s",
                     review_id, ticker, outcome, severity)

        return review

    def _generate_lesson(
        self,
        ticker: str,
        outcome: str,
        thesis_correct: bool | None,
        what_went_right: list[str],
        what_went_wrong: list[str],
    ) -> str:
        """Gera lição aprendida do trade."""
        if outcome == "win":
            if thesis_correct:
                return f"Para {ticker}: Tese confirmada leva a wins. Replicar análise similar."
            else:
                return f"Para {ticker}: Win apesar de tese incorreta. Revisar tese - pode ter sido sorte."
        elif outcome == "loss":
            if what_went_wrong:
                return f"Para {ticker}: Evitar - {', '.join(what_went_wrong)}."
            else:
                return f"Para {ticker}: Perda sem causa clara. Revisar processo de entrada."
        else:
            return f"Para {ticker}: Breakeven - analisar se valeu o risco."

    def review_batch(
        self,
        trades: list[dict[str, Any]],
    ) -> list[TradeReview]:
        """Analisa um lote de trades.

        Args:
            trades: Lista de trades

        Returns:
            Lista de reviews
        """
        reviews = []
        for trade in trades:
            try:
                review = self.review_trade(trade)
                reviews.append(review)
            except Exception as e:
                logger.warning("Failed to review trade %s: %s",
                              trade.get("trade_id", "?"), e)
        return reviews

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas de reviews."""
        if not self._log_path.exists():
            return {"total_reviews": 0}

        reviews = []
        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        reviews.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not reviews:
            return {"total_reviews": 0}

        total = len(reviews)
        wins = sum(1 for r in reviews if r.get("outcome") == "win")
        losses = sum(1 for r in reviews if r.get("outcome") == "loss")
        high_severity = sum(1 for r in reviews if r.get("severity") == "high")
        verdict_matches = sum(1 for r in reviews if r.get("verdict_match"))

        return {
            "total_reviews": total,
            "wins": wins,
            "losses": losses,
            "high_severity": high_severity,
            "verdict_match_rate": verdict_matches / total if total > 0 else 0,
        }


# Singleton
_post_trade_reviewer: PostTradeReviewer | None = None


def get_post_trade_reviewer() -> PostTradeReviewer:
    """Retorna singleton de PostTradeReviewer."""
    global _post_trade_reviewer
    if _post_trade_reviewer is None:
        _post_trade_reviewer = PostTradeReviewer()
        logger.info("PostTradeReviewer initialized")
    return _post_trade_reviewer


if __name__ == "__main__":
    # Test mode
    reviewer = get_post_trade_reviewer()

    # Trade de teste
    test_trade = {
        "trade_id": "test_001",
        "ticker": "AAPL",
        "verdict_at_entry": "Confidence 75% - Strong buy on breakout with volume confirmation",
        "outcome": "win",
        "pnl_amount": 150.0,
        "pnl_percent": 3.0,
        "thesis_correct": True,
        "thesis": "Breakout above $180 with strong volume",
        "entry_price": 182.0,
        "exit_price": 187.5,
        "exit_reason": "take_profit",
    }

    review = reviewer.review_trade(test_trade)

    print(f"Review: {review.review_id}")
    print(f"Severity: {review.severity}")
    print(f"Verdict match: {review.verdict_match}")
    print(f"What went right: {review.what_went_right}")
    print(f"Lesson: {review.lesson_learned}")
