"""Feedback Loop - Sistema de aprendizado de trades.

Analisa trades fechados, extrai lições aprendidas e injeta no contexto do Bob
para calibrar decisões futuras.

Arquitetura:
1. PatternAnalyzer - identifica padrões em trades bem-sucedidos vs mal-sucedidos
2. LessonExtractor - extrai lições aprendidas de trades fechados
3. LearningLog - registro estruturado de descobertas
4. FeedbackLoop - orquestra o fluxo de aprendizado
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LEARNING_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "learning_log.jsonl"
)


def _parse_utc_datetime(value: Any) -> datetime | None:
    """Parse ISO timestamps emitted by the local JSONL journals."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_confidence(value: Any) -> float | None:
    """Extract a Bob confidence value from verdict text and normalize to 0..1."""
    if value is None:
        return None
    text = str(value)
    patterns = (
        r"(?:confidence|confianca|confian.a|conf)\D{0,16}(\d{1,3}(?:\.\d+)?)",
        r"(\d{1,3}(?:\.\d+)?)\s*/\s*100",
        r"(\d{1,3}(?:\.\d+)?)\s*%",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw = float(match.group(1))
        normalized = raw / 100 if raw > 1 else raw
        return max(0.0, min(normalized, 1.0))
    return None


@dataclass
class Pattern:
    """Padrão identificado em trades."""
    pattern_id: str
    description: str
    win_rate: float  # 0-1
    avg_pnl: float
    sample_size: int
    last_seen: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Lesson:
    """Lição aprendida de um trade ou conjunto de trades."""
    lesson_id: str
    title: str
    content: str
    source_trade_ids: list[str]
    confidence: float  # 0-1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    category: str = "general"  # "entry" | "exit" | "thesis" | "risk" | "sector"
    applicable_tickers: list[str] = field(default_factory=list)
    pain_score: float = 0.0  # 0-1, quão dolorosa foi a lição (para XP system)
    xp_impact: int = 0  # Impacto em XP (negativo = lição de erro, positivo = lição de sucesso)


class PatternAnalyzer:
    """Analisa padrões em trades bem-sucedidos vs mal-sucedidos."""

    def __init__(self, journal):
        self._journal = journal
        self._cache = None
        self._cache_time = None

    def _get_trades(self) -> list[dict]:
        """Carrega trades do journal com cache."""
        now = datetime.now(timezone.utc)
        if self._cache and self._cache_time and (now - self._cache_time).seconds < 300:
            return self._cache

        trades = self._journal.list_all()
        # Apenas trades fechados com outcome
        closed = [
            t for t in trades
            if t.get("outcome") in {"win", "loss", "breakeven"}
            and t.get("exit_date")
        ]
        self._cache = closed
        self._cache_time = now
        return closed

    def analyze_sector_performance(self) -> list[Pattern]:
        """Analisa performance por setor/setor."""
        trades = self._get_trades()
        if not trades:
            return []

        # Extrai setor dos tickers (simulado - na prática usaria dados reais)
        sectors = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "count": 0})

        for trade in trades:
            ticker = trade.get("ticker", "")
            outcome = trade.get("outcome", "")
            pnl = trade.get("pnl_amount") or 0.0

            # Setor simplificado baseado em ticker (na prática usar API)
            sector = self._classify_sector(ticker)

            sectors[sector]["count"] += 1
            sectors[sector]["pnl"] += pnl
            if outcome == "win":
                sectors[sector]["wins"] += 1
            elif outcome == "loss":
                sectors[sector]["losses"] += 1

        patterns = []
        for sector, stats in sectors.items():
            if stats["count"] < 3:
                continue
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0
            avg_pnl = stats["pnl"] / stats["count"]

            patterns.append(Pattern(
                pattern_id=f"sector_{sector}",
                description=f"Performance em {sector}",
                win_rate=win_rate,
                avg_pnl=avg_pnl,
                sample_size=stats["count"],
                last_seen=datetime.now(timezone.utc).isoformat(),
                tags=["sector", "performance"]
            ))

        return sorted(patterns, key=lambda p: p.win_rate, reverse=True)

    def analyze_holding_period_performance(self) -> list[Pattern]:
        """Analisa performance por período de holding."""
        trades = self._get_trades()
        if not trades:
            return []

        periods = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "count": 0})

        for trade in trades:
            entry = _parse_utc_datetime(trade.get("entry_date"))
            exit_str = trade.get("exit_date")
            if not exit_str:
                continue
            exit_date = _parse_utc_datetime(exit_str)
            if entry is None or exit_date is None:
                continue

            duration_hours = (exit_date - entry).total_seconds() / 3600

            # Classifica período
            if duration_hours < 24:
                period = "day_trade"
            elif duration_hours < 24 * 7:
                period = "swing"
            else:
                period = "position"

            outcome = trade.get("outcome", "")
            pnl = trade.get("pnl_amount") or 0.0

            periods[period]["count"] += 1
            periods[period]["pnl"] += pnl
            if outcome == "win":
                periods[period]["wins"] += 1
            elif outcome == "loss":
                periods[period]["losses"] += 1

        patterns = []
        for period, stats in periods.items():
            if stats["count"] < 2:
                continue
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0
            avg_pnl = stats["pnl"] / stats["count"]

            patterns.append(Pattern(
                pattern_id=f"period_{period}",
                description=f"Performance em trades {period}",
                win_rate=win_rate,
                avg_pnl=avg_pnl,
                sample_size=stats["count"],
                last_seen=datetime.now(timezone.utc).isoformat(),
                tags=["holding_period", "performance"]
            ))

        return sorted(patterns, key=lambda p: p.win_rate, reverse=True)

    def analyze_thesis_accuracy(self) -> list[Pattern]:
        """Analisa precisão das teses formuladas."""
        trades = self._get_trades()
        if not trades:
            return []

        thesis_accuracy = defaultdict(lambda: {"correct": 0, "total": 0})

        for trade in trades:
            thesis = trade.get("thesis", "").lower()
            thesis_correct = trade.get("thesis_correct")

            if thesis_correct is None:
                continue

            # Extrai palavras-chave da tese
            keywords = self._extract_thesis_keywords(thesis)
            for keyword in keywords:
                thesis_accuracy[keyword]["total"] += 1
                if thesis_correct:
                    thesis_accuracy[keyword]["correct"] += 1

        patterns = []
        for keyword, stats in thesis_accuracy.items():
            if stats["total"] < 2:
                continue
            accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0

            patterns.append(Pattern(
                pattern_id=f"thesis_{keyword}",
                description=f"Precisão de tese: {keyword}",
                win_rate=accuracy,
                avg_pnl=0.0,  # N/A para thesis accuracy
                sample_size=stats["total"],
                last_seen=datetime.now(timezone.utc).isoformat(),
                tags=["thesis", "accuracy"]
            ))

        return sorted(patterns, key=lambda p: p.win_rate, reverse=True)

    def _classify_sector(self, ticker: str) -> str:
        """Classifica setor baseado no ticker (simplificado)."""
        ticker = ticker.upper()

        # Mapeamento simplificado (na prática usar API)
        sector_map = {
            # Tech
            "NVDA": "semiconductors",
            "AMD": "semiconductors",
            "AAPL": "tech_hardware",
            "MSFT": "software",
            "GOOGL": "software",
            "TSLA": "ev_tech",

            # Energy
            "XOM": "oil_gas",
            "CVX": "oil_gas",
            "COP": "oil_gas",

            # Finance
            "JPM": "banking",
            "BAC": "banking",
            "WFC": "banking",

            # Healthcare
            "JNJ": "healthcare",
            "PFE": "pharma",
            "UNH": "healthcare",
        }

        return sector_map.get(ticker, "other")

    def _extract_thesis_keywords(self, thesis: str) -> list[str]:
        """Extrai palavras-chave da tese."""
        keywords = []
        thesis_lower = thesis.lower()

        # Palavras-chave comuns
        keyword_patterns = {
            "breakout": "breakout",
            "momentum": "momentum",
            "dip": "dip_buying",
            "earnings": "earnings_catalyst",
            "news": "news_catalyst",
            "trend": "trend_following",
            "reversal": "reversal",
            "volume": "volume_spike",
        }

        for pattern, keyword in keyword_patterns.items():
            if pattern in thesis_lower:
                keywords.append(keyword)

        return keywords

    def analyze_risk_reward_performance(self) -> list[Pattern]:
        """Analisa performance por perfil de risco."""
        trades = self._get_trades()
        if not trades:
            return []

        risk_levels = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0, "count": 0})

        for trade in trades:
            risk = trade.get("risk_assessment", "").lower()
            outcome = trade.get("outcome", "")
            pnl = trade.get("pnl_amount") or 0.0

            if not risk:
                continue

            # Normaliza risco
            if any(w in risk for w in ["alto", "high", "agressivo"]):
                level = "high"
            elif any(w in risk for w in ["baixo", "low", "conserv"]):
                level = "low"
            else:
                level = "moderate"

            risk_levels[level]["count"] += 1
            risk_levels[level]["pnl"] += pnl
            if outcome == "win":
                risk_levels[level]["wins"] += 1
            elif outcome == "loss":
                risk_levels[level]["losses"] += 1

        patterns = []
        for level, stats in risk_levels.items():
            if stats["count"] < 2:
                continue
            win_rate = stats["wins"] / stats["count"] if stats["count"] > 0 else 0
            avg_pnl = stats["pnl"] / stats["count"]

            patterns.append(Pattern(
                pattern_id=f"risk_{level}",
                description=f"Performance com risco {level}",
                win_rate=win_rate,
                avg_pnl=avg_pnl,
                sample_size=stats["count"],
                last_seen=datetime.now(timezone.utc).isoformat(),
                tags=["risk", "performance"]
            ))

        return sorted(patterns, key=lambda p: p.win_rate, reverse=True)


class LessonExtractor:
    """Extrai lições aprendidas de trades fechados."""

    def __init__(self, journal):
        self._journal = journal

    def extract_from_recent_trades(self, hours: int = 168) -> list[Lesson]:
        """Extrai lições de trades recentes (default: 7 dias)."""
        trades = self._journal.list_all()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        recent = []
        for t in trades:
            exit_date = t.get("exit_date")
            if exit_date:
                parsed_exit = _parse_utc_datetime(exit_date)
                if parsed_exit is None:
                    continue
                if parsed_exit > cutoff:
                    recent.append(t)

        lessons = []

        # 1. Lições de trades com perdas grandes
        for trade in recent:
            pnl = trade.get("pnl_amount") or 0
            if pnl < -100:  # Perda > $100
                lessons.append(self._lesson_from_loss(trade))

        # 2. Lições de padrões de wins
        wins = [t for t in recent if t.get("outcome") == "win"]
        if len(wins) >= 3:
            lessons.append(self._lesson_from_win_streak(wins))

        # 3. Lições de vereditos incorretos
        for trade in recent:
            if trade.get("thesis_correct") is False:
                lessons.append(self._lesson_from_broken_thesis(trade))

        return lessons

    def _lesson_from_loss(self, trade: dict) -> Lesson:
        """Extrai lição de uma perda."""
        ticker = trade.get("ticker", "")
        pnl = trade.get("pnl_amount") or 0
        thesis = trade.get("thesis", "")
        exit_reason = trade.get("exit_reason", "")
        lesson = trade.get("lesson_learned", "")

        title = f"Perda em {ticker}: ${abs(pnl):.2f}"

        content = f"""
Trade: {ticker} ({trade.get('direction', 'unknown')})
Entrada: ${trade.get('entry_price', 0):.2f}
Saída: ${trade.get('exit_price', 0):.2f}
PnL: ${pnl:.2f}
Tese original: {thesis[:200]}
Razão da saída: {exit_reason}

Lição aprendida: {lesson or 'Análise pendente - revisar trade'}
""".strip()

        return Lesson(
            lesson_id=f"loss_{ticker}_{trade.get('trade_id', '')[:8]}",
            title=title,
            content=content,
            source_trade_ids=[trade.get("trade_id", "")],
            confidence=0.7,
            category="risk",
            applicable_tickers=[ticker]
        )

    def _lesson_from_win_streak(self, wins: list[dict]) -> Lesson:
        """Extrai lição de uma sequência de wins."""
        tickers = [w.get("ticker", "") for w in wins]
        total_pnl = sum(w.get("pnl_amount") or 0 for w in wins)

        # Analisa padrões comuns
        common_themes = []
        for win in wins:
            thesis = win.get("thesis", "").lower()
            if "momentum" in thesis:
                common_themes.append("momentum")
            if "breakout" in thesis:
                common_themes.append("breakout")
            if "earnings" in thesis:
                common_themes.append("earnings")

        theme = max(set(common_themes), key=common_themes.count) if common_themes else "diversos"

        title = f"Padrão de {len(wins)} wins consecutivos"
        content = f"""
Tickers: {', '.join(tickers)}
PnL total: ${total_pnl:.2f}
Tema comum: {theme}

O que funcionou:
- Entrada em momentum identificado
- Gestão de risco respeitada
- Saída em target atingido

Replicar: Buscar setups similares com {theme} confirmado.
""".strip()

        return Lesson(
            lesson_id=f"streak_{len(wins)}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            title=title,
            content=content,
            source_trade_ids=[w.get("trade_id", "") for w in wins],
            confidence=0.8,
            category="thesis"
        )

    def _lesson_from_broken_thesis(self, trade: dict) -> Lesson:
        """Extrai lição de tese quebrada."""
        ticker = trade.get("ticker", "")
        thesis = trade.get("thesis", "")
        what_went_wrong = trade.get("what_went_wrong", "")

        title = f"Tese incorreta em {ticker}"
        content = f"""
Tese original: {thesis[:200]}

O que deu errado: {what_went_wrong or 'Análise pendente'}

Ação corretiva:
- Revisar premissas da tese
- Verificar se catalyst era verificado
- Checar se timing estava adiantado
""".strip()

        return Lesson(
            lesson_id=f"broken_thesis_{ticker}_{trade.get('trade_id', '')[:8]}",
            title=title,
            content=content,
            source_trade_ids=[trade.get("trade_id", "")],
            confidence=0.6,
            category="thesis",
            applicable_tickers=[ticker]
        )


class LearningLog:
    """Registro estruturado de lições aprendidas."""

    def __init__(self, path: Path | None = None):
        self._path = path or DEFAULT_LEARNING_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lessons: dict[str, Lesson] = {}
        self._load()

    def _load(self) -> None:
        """Carrega lições do disco."""
        if not self._path.exists():
            return

        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        lesson = Lesson(**data)
                        self._lessons[lesson.lesson_id] = lesson
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning("Skipping corrupt lesson line: %s", e)

    def _save(self, lesson: Lesson) -> None:
        """Salva lição no disco (append-only)."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(lesson.__dict__, ensure_ascii=False) + "\n")

    def add_lesson(self, lesson: Lesson) -> None:
        """Adiciona lição ao log."""
        if lesson.lesson_id in self._lessons:
            logger.debug("Lesson %s already exists, updating", lesson.lesson_id)

        self._lessons[lesson.lesson_id] = lesson
        self._save(lesson)
        logger.info("Lesson added: %s", lesson.title)

    def get_recent_lessons(self, days: int = 7, category: str = "") -> list[Lesson]:
        """Retorna lições recentes."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        recent = [
            lesson for lesson in self._lessons.values()
            if (_parse_utc_datetime(lesson.created_at) or datetime.min.replace(tzinfo=timezone.utc))
            > cutoff
            and (not category or lesson.category == category)
        ]

        return sorted(recent, key=lambda lesson: lesson.created_at, reverse=True)

    def render_for_bob(self, max_chars: int = 1500) -> str:
        """Renderiza lições para o prompt do Bob."""
        recent = self.get_recent_lessons(days=30)

        if not recent:
            return ""

        lines = ["\n=== LIÇÕES APRENDIDAS (últimos 30 dias) ===\n"]

        used = len("\n".join(lines))
        for lesson in recent[:5]:  # Max 5 lições
            entry = f"• {lesson.title}\n  {lesson.content[:150]}...\n"
            if used + len(entry) > max_chars:
                break
            lines.append(entry)
            used += len(entry)

        lines.append("=== FIM DAS LIÇÕES ===\n")
        return "\n".join(lines)


class FeedbackLoop:
    """Orquestra o fluxo de aprendizado."""

    def __init__(
        self,
        journal_path: Path | None = None,
        learning_log_path: Path | None = None,
        conversation_memory: Any | None = None,
        xp_system: Any | None = None,
    ):
        from core.trading.paper_journal import PaperJournal

        self._journal = PaperJournal(journal_path)
        self._learning_log = LearningLog(learning_log_path)
        self._pattern_analyzer = PatternAnalyzer(self._journal)
        self._lesson_extractor = LessonExtractor(self._journal)
        self._conversation_memory = conversation_memory
        self._xp_system = xp_system  # XPSystem opcional (singleton se None)

    def run_learning_cycle(self, *, record_memory: bool = True) -> dict[str, Any]:
        """Executa um ciclo completo de aprendizado."""
        logger.info("Starting learning cycle...")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "theses_closed": 0,
            "theses_closed_items": [],
            "patterns_found": 0,
            "lessons_extracted": 0,
            "patterns": [],
            "lessons": [],
            "bias_report": {},
        }

        try:
            closed_theses = self._journal.review_aged_closed_theses(
                record_memory=record_memory,
                memory=self._conversation_memory,
            )
            results["theses_closed_items"] = closed_theses
            results["theses_closed"] = len(closed_theses)
            if closed_theses:
                logger.info("Closed %d aged theses", len(closed_theses))
        except Exception as e:
            logger.warning("Aged thesis review failed: %s", e)

        # 1. Analisa padrões
        try:
            sector_patterns = self._pattern_analyzer.analyze_sector_performance()
            period_patterns = self._pattern_analyzer.analyze_holding_period_performance()
            thesis_patterns = self._pattern_analyzer.analyze_thesis_accuracy()
            risk_patterns = self._pattern_analyzer.analyze_risk_reward_performance()

            all_patterns = sector_patterns + period_patterns + thesis_patterns + risk_patterns
            results["patterns"] = [pattern.__dict__ for pattern in all_patterns]
            results["patterns_found"] = len(all_patterns)

            logger.info("Found %d patterns", len(all_patterns))
        except Exception as e:
            logger.warning("Pattern analysis failed: %s", e)

        # 2. Extrai lições
        try:
            lessons = self._lesson_extractor.extract_from_recent_trades(hours=168)
            for lesson in lessons:
                self._learning_log.add_lesson(lesson)

            results["lessons"] = [lesson.__dict__ for lesson in lessons]
            results["lessons_extracted"] = len(lessons)

            logger.info("Extracted %d lessons", len(lessons))
        except Exception as e:
            logger.warning("Lesson extraction failed: %s", e)

        try:
            results["bias_report"] = self.analyze_confidence_bias()
        except Exception as e:
            logger.warning("Bias analysis failed: %s", e)

        # 3. Atualiza XP baseado em trades fechados
        try:
            xp_results = self._update_xp_from_closed_trades()
            results["xp_updates"] = xp_results
            logger.info("XP updated: %d events", len(xp_results.get("events", [])))
        except Exception as e:
            logger.warning("XP update failed: %s", e)

        # 4. Gera relatório para Bob
        try:
            bob_context = self.render_for_bob()
            results["bob_context"] = bob_context
            logger.info("Generated Bob context (%d chars)", len(bob_context))
        except Exception as e:
            logger.warning("Bob context generation failed: %s", e)

        logger.info("Learning cycle complete: %d patterns, %d lessons",
                    results["patterns_found"], results["lessons_extracted"])

        return results

    def analyze_confidence_bias(self, min_closed: int = 10) -> dict[str, Any]:
        """Compare Bob confidence at entry with real closed-trade outcomes."""
        closed = [
            trade
            for trade in self._journal.list_closed()
            if trade.get("outcome") in {"win", "loss", "breakeven"}
        ]

        base_report: dict[str, Any] = {
            "status": "insufficient_sample",
            "bias": "insufficient_sample",
            "sample_size": len(closed),
            "confidence_sample_size": 0,
            "min_sample": min_closed,
        }
        if len(closed) < min_closed:
            return base_report

        samples = []
        for trade in closed:
            confidence = _extract_confidence(trade.get("verdict_at_entry"))
            if confidence is None:
                continue
            samples.append((trade, confidence))

        if not samples:
            return {
                **base_report,
                "status": "missing_confidence_data",
                "bias": "confidence_not_recorded",
                "confidence_sample_size": 0,
            }

        wins = sum(1 for trade, _confidence in samples if trade.get("outcome") == "win")
        win_rate = wins / len(samples)
        avg_confidence = sum(confidence for _trade, confidence in samples) / len(samples)
        calibration_gap = avg_confidence - win_rate

        if calibration_gap >= 0.20:
            bias = "overconfidence"
            recommendation = "Raise entry threshold or demand stronger confirmation."
        elif calibration_gap <= -0.20:
            bias = "underconfidence"
            recommendation = "Allow higher-quality setups to size up within paper limits."
        else:
            bias = "calibrated"
            recommendation = "Keep current confidence threshold and continue collecting trades."

        high_conf_losses = [
            trade.get("trade_id")
            for trade, confidence in samples
            if confidence >= 0.70 and trade.get("outcome") == "loss"
        ]
        low_conf_wins = [
            trade.get("trade_id")
            for trade, confidence in samples
            if confidence <= 0.50 and trade.get("outcome") == "win"
        ]

        return {
            "status": "analyzed",
            "bias": bias,
            "sample_size": len(closed),
            "confidence_sample_size": len(samples),
            "min_sample": min_closed,
            "win_rate": round(win_rate, 4),
            "avg_confidence": round(avg_confidence, 4),
            "calibration_gap": round(calibration_gap, 4),
            "high_confidence_losses": high_conf_losses,
            "low_confidence_wins": low_conf_wins,
            "recommendation": recommendation,
        }

    def render_for_bob(self, max_chars: int = 2000) -> str:
        """Renderiza insights completos para o Bob."""
        sections = []

        # 1. Lições aprendidas
        lessons_text = self._learning_log.render_for_bob(max_chars=max_chars // 2)
        if lessons_text:
            sections.append(lessons_text)

        # 2. Padrões de performance
        patterns = []
        try:
            sector_patterns = self._pattern_analyzer.analyze_sector_performance()
            if sector_patterns:
                top_sector = sector_patterns[0]
                patterns.append(f"• Melhor setor: {top_sector.description} (win rate: {top_sector.win_rate*100:.0f}%)")

            period_patterns = self._pattern_analyzer.analyze_holding_period_performance()
            if period_patterns:
                top_period = period_patterns[0]
                patterns.append(f"• Melhor período: {top_period.description} (win rate: {top_period.win_rate*100:.0f}%)")

            risk_patterns = self._pattern_analyzer.analyze_risk_reward_performance()
            if risk_patterns:
                top_risk = risk_patterns[0]
                patterns.append(f"• Melhor risco: {top_risk.description} (win rate: {top_risk.win_rate*100:.0f}%)")
        except Exception as e:
            logger.warning("Pattern rendering failed: %s", e)

        if patterns:
            sections.append("\n=== PADRÕES DE PERFORMANCE ===\n")
            sections.extend(patterns)
            sections.append("\n=== FIM DOS PADRÕES ===\n")

        bias_report = self.analyze_confidence_bias()
        if bias_report.get("status") == "analyzed":
            sections.append("\n=== CALIBRACAO BOB VS OUTCOME ===\n")
            sections.append(
                f"* Bias: {bias_report['bias']} | "
                f"conf_media={bias_report['avg_confidence'] * 100:.1f}% | "
                f"win_rate={bias_report['win_rate'] * 100:.1f}%"
            )
            sections.append(f"* Acao: {bias_report['recommendation']}")
            sections.append("\n=== FIM DA CALIBRACAO ===\n")

        # 4. XP & Level (se disponível)
        if self._xp_system is None:
            try:
                from .xp_system import get_xp_system
                self._xp_system = get_xp_system()
            except ImportError:
                pass

        if self._xp_system:
            xp_text = self._xp_system.render_for_bob(max_chars=800)
            if xp_text:
                sections.append(xp_text)

        return "\n".join(sections)

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do sistema de aprendizado."""
        trades = self._journal.list_all()
        closed = [trade for trade in trades if trade.get("exit_date")]

        wins = sum(1 for trade in closed if trade.get("outcome") == "win")
        losses = sum(1 for trade in closed if trade.get("outcome") == "loss")
        if self._learning_log._lessons:
            latest_lesson = max(
                self._learning_log._lessons.values(),
                key=lambda lesson: lesson.created_at,
            )
            last_learning_cycle = latest_lesson.created_at
        else:
            last_learning_cycle = None

        return {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(closed) if closed else 0,
            "lessons_logged": len(self._learning_log._lessons),
            "last_learning_cycle": last_learning_cycle,
            "bias_report": self.analyze_confidence_bias(),
        }


    def check_before_trade(self, ticker: str, thesis: str = "") -> str | None:
        """Verifica se este trade é similar a um que falhou. Retorna motivo ou None."""
        ticker = ticker.upper()
        closed = [t for t in self._journal.list_all()
                  if str(t.get("ticker","")).upper() == ticker and t.get("outcome") == "loss"]
        if not closed:
            return None

        last_loss = closed[-1]
        loss_thesis = str(last_loss.get("thesis","") or last_loss.get("entry_reasoning",""))
        loss_trade_id = str(last_loss.get("trade_id","?"))

        # Similarity check: same ticker + overlapping keywords = block
        thesis_words = set(thesis.lower().split()) if thesis else set()
        loss_words = set(loss_thesis.lower().split())
        overlap = len(thesis_words & loss_words) if thesis_words else 0

        if ticker in [str(t.get("ticker","")).upper() for t in closed]:
            return f"FeedbackLoop: {ticker} already has {len(closed)} loss(es). Last: {loss_trade_id}. Review thesis before retrying."

        if overlap >= 3:
            return f"FeedbackLoop: thesis similar to failed trade {loss_trade_id} ({loss_thesis[:80]}...)"

        return None

    def calibrate_confidence(self) -> dict:
        """Compara confidence declarada vs outcome real. Retorna fator de calibragem."""
        closed = [t for t in self._journal.list_all() if t.get("outcome") in ("win","loss")]
        samples = []
        for t in closed:
            conf = t.get("confidence")
            if conf is not None and isinstance(conf, (int,float)) and 0 <= conf <= 100:
                samples.append((conf, t.get("outcome")))

        if len(samples) < 5:
            return {"status": "insufficient_data", "sample_size": len(samples), "min_sample": 5, "factor": 1.0}

        # For each sample: if confidence > 50 and outcome=loss → overconfident
        overconfident = sum(1 for c,o in samples if c > 60 and o == "loss")
        underconfident = sum(1 for c,o in samples if c < 40 and o == "win")
        total = len(samples)

        # Calibration factor: actual_win_rate / avg_confidence
        wins = sum(1 for _,o in samples if o == "win")
        actual_wr = wins / total if total > 0 else 0
        avg_conf = sum(c for c,_ in samples) / total / 100 if total > 0 else 0.5

        factor = actual_wr / avg_conf if avg_conf > 0 else 1.0
        factor = max(0.3, min(3.0, factor))  # clamp

        return {
            "status": "calibrated",
            "sample_size": total,
            "wins": wins,
            "actual_win_rate": round(actual_wr, 3),
            "avg_confidence": round(avg_conf, 3),
            "calibration_factor": round(factor, 3),
            "overconfident_losses": overconfident,
            "underconfident_wins": underconfident,
            "interpretation": (
                f"Bob is {'overconfident' if factor < 0.8 else 'underconfident' if factor > 1.2 else 'calibrated'}. "
                f"Actual win rate {actual_wr:.0%} vs declared confidence {avg_conf:.0%}. "
                f"Suggested confidence multiplier: {factor:.2f}"
            )
        }

    def _update_xp_from_closed_trades(self) -> dict[str, Any]:
        """Atualiza XP baseado em trades fechados recentemente.

        Returns:
            Dict com eventos de XP criados
        """
        if self._xp_system is None:
            try:
                from .xp_system import get_xp_system
                self._xp_system = get_xp_system()
            except ImportError:
                return {"status": "xp_system_unavailable", "events": []}

        # Buscar trades fechados nas últimas 24h que não foram processados para XP
        closed_trades = self._journal.list_closed()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        events = []
        win_count = 0
        loss_count = 0

        for trade in closed_trades:
            trade_id = trade.get("trade_id", "")
            exit_date_str = trade.get("exit_date", "")

            # Pular trades sem data de saída ou muito antigos
            if not exit_date_str:
                continue

            try:
                exit_date = _parse_utc_datetime(exit_date_str)
                if exit_date is None or exit_date < cutoff:
                    continue
            except Exception:
                continue

            outcome = trade.get("outcome", "")
            pnl = trade.get("pnl_amount") or 0
            thesis_correct = trade.get("thesis_correct")
            context = {
                "trade_id": trade_id,
                "ticker": trade.get("ticker", ""),
                "pnl_amount": pnl,
                "thesis_correct": thesis_correct,
                "exit_reason": trade.get("exit_reason", ""),
            }

            # Registrar outcome no XP system
            try:
                event = self._xp_system.record_trade_outcome(
                    outcome=outcome,
                    pnl_amount=pnl,
                    thesis_correct=thesis_correct,
                    trade_id=trade_id,
                    context=context,
                )
                if event:
                    events.append(event.to_dict())

                    if outcome == "win":
                        win_count += 1
                    elif outcome == "loss":
                        loss_count += 1
            except Exception as e:
                logger.warning("Failed to record XP for trade %s: %s", trade_id, e)

        # Registrar streaks
        if win_count >= 3:
            try:
                streak_event = self._xp_system.record_streak("win", win_count)
                events.append(streak_event.to_dict())
            except Exception as e:
                logger.warning("Failed to record win streak: %s", e)

        elif loss_count >= 3:
            try:
                streak_event = self._xp_system.record_streak("loss", loss_count)
                events.append(streak_event.to_dict())
            except Exception as e:
                logger.warning("Failed to record loss streak: %s", e)

        return {
            "status": "updated",
            "events_count": len(events),
            "events": events,
            "win_count": win_count,
            "loss_count": loss_count,
        }

    def record_trade_confidence(self, trade_id: str, confidence: float) -> bool:
        """Atualiza o confidence de um trade no journal."""
        trades = self._journal.list_all()
        for t in trades:
            if str(t.get("trade_id","")) == str(trade_id):
                t["confidence"] = round(float(confidence), 1)
                # Re-write journal with updated confidence
                self._journal._rewrite(trades)
                logger.info("FeedbackLoop: recorded confidence %.1f for trade %s", confidence, trade_id)
                return True
        return False


# Singleton
_feedback_loop: FeedbackLoop | None = None


def get_feedback_loop() -> FeedbackLoop:
    """Retorna singleton de FeedbackLoop."""
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
        logger.info("FeedbackLoop initialized")
    return _feedback_loop
