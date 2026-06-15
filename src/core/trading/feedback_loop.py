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
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LEARNING_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "learning_log.jsonl"
)


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
            entry = datetime.fromisoformat(trade.get("entry_date", ""))
            exit_str = trade.get("exit_date")
            if not exit_str:
                continue
            exit_date = datetime.fromisoformat(exit_str)

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
                try:
                    if datetime.fromisoformat(exit_date) > cutoff:
                        recent.append(t)
                except (ValueError, TypeError):
                    continue

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
            l for l in self._lessons.values()
            if datetime.fromisoformat(l.created_at) > cutoff
            and (not category or l.category == category)
        ]

        return sorted(recent, key=lambda l: l.created_at, reverse=True)

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

    def __init__(self, journal_path: Path | None = None, learning_log_path: Path | None = None):
        from core.trading.paper_journal import PaperJournal

        self._journal = PaperJournal(journal_path)
        self._learning_log = LearningLog(learning_log_path)
        self._pattern_analyzer = PatternAnalyzer(self._journal)
        self._lesson_extractor = LessonExtractor(self._journal)

    def run_learning_cycle(self) -> dict[str, Any]:
        """Executa um ciclo completo de aprendizado."""
        logger.info("Starting learning cycle...")

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patterns_found": 0,
            "lessons_extracted": 0,
            "patterns": [],
            "lessons": []
        }

        # 1. Analisa padrões
        try:
            sector_patterns = self._pattern_analyzer.analyze_sector_performance()
            period_patterns = self._pattern_analyzer.analyze_holding_period_performance()
            thesis_patterns = self._pattern_analyzer.analyze_thesis_accuracy()
            risk_patterns = self._pattern_analyzer.analyze_risk_reward_performance()

            all_patterns = sector_patterns + period_patterns + thesis_patterns + risk_patterns
            results["patterns"] = [p.__dict__ for p in all_patterns]
            results["patterns_found"] = len(all_patterns)

            logger.info("Found %d patterns", len(all_patterns))
        except Exception as e:
            logger.warning("Pattern analysis failed: %s", e)

        # 2. Extrai lições
        try:
            lessons = self._lesson_extractor.extract_from_recent_trades(hours=168)
            for lesson in lessons:
                self._learning_log.add_lesson(lesson)

            results["lessons"] = [l.__dict__ for l in lessons]
            results["lessons_extracted"] = len(lessons)

            logger.info("Extracted %d lessons", len(lessons))
        except Exception as e:
            logger.warning("Lesson extraction failed: %s", e)

        # 3. Gera relatório para Bob
        try:
            bob_context = self.render_for_bob()
            results["bob_context"] = bob_context
            logger.info("Generated Bob context (%d chars)", len(bob_context))
        except Exception as e:
            logger.warning("Bob context generation failed: %s", e)

        logger.info("Learning cycle complete: %d patterns, %d lessons",
                    results["patterns_found"], results["lessons_extracted"])

        return results

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

        return "\n".join(sections)

    def get_stats(self) -> dict[str, Any]:
        """Retorna estatísticas do sistema de aprendizado."""
        trades = self._journal.list_all()
        closed = [t for t in trades if t.get("exit_date")]

        wins = sum(1 for t in closed if t.get("outcome") == "win")
        losses = sum(1 for t in closed if t.get("outcome") == "loss")

        return {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(closed) if closed else 0,
            "lessons_logged": len(self._learning_log._lessons),
            "last_learning_cycle": self._learning_log._lessons[max(self._learning_log._lessons.keys(), key=lambda k: self._learning_log._lessons[k].created_at)].created_at if self._learning_log._lessons else None,
        }


# Singleton
_feedback_loop: FeedbackLoop | None = None


def get_feedback_loop() -> FeedbackLoop:
    """Retorna singleton de FeedbackLoop."""
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
        logger.info("FeedbackLoop initialized")
    return _feedback_loop
