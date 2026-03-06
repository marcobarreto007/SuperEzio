"""
f51 unified core — detectores.
SpiderSense (armadilhas) + HeuristicUncertainty (dificuldade).
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from .formulas import heuristic_uncertainty as hu

# =============================================================================
# TRAP PATTERNS
# =============================================================================


@dataclass
class TrapPattern:
    name: str
    regex: str = ""
    keywords: list[str] = field(default_factory=list)
    danger: float = 0.5
    warning: str = ""
    category: str = "general"


TRAP_PATTERNS: list[TrapPattern] = [
    # --- Edge cases ---
    TrapPattern(
        "universal_quantifier",
        r"\b(for all|para todo|for every)\b",
        danger=0.6,
        category="edge_case",
        warning="Verificar n=0, n=1, casos extremos",
    ),
    TrapPattern(
        "positive_integers",
        r"\b(positive integers?|inteiros? positivos)\b",
        danger=0.5,
        category="edge_case",
        warning="Exclui zero! Verificar se zero é a pegadinha",
    ),
    # --- Distractions ---
    TrapPattern(
        "year_number",
        r"\b(202[4-9])\b",
        danger=0.8,
        category="distraction",
        warning="Ano = CLASSIC TRAP! Só importa módulo",
    ),
    TrapPattern(
        "huge_number",
        r"\b\d{6,}\b",
        danger=0.7,
        category="distraction",
        warning="Número grande é distração! Procurar padrão",
    ),
    # --- False confidence ---
    TrapPattern(
        "obvious_trap",
        r"\b(obviously|clearly|trivially|óbvio)\b",
        danger=0.9,
        category="false_confidence",
        warning="Se é óbvio POR QUE PERGUNTAR? Armadilha!",
    ),
    TrapPattern(
        "simple_trap",
        r"\b(simple|simples|easy|fácil)\b",
        danger=0.7,
        category="false_confidence",
        warning="Problema 'simples' em competição = pegadinha",
    ),
    # --- Adversarial ---
    TrapPattern(
        "system_override",
        r"\b(ignore (previous|all)|esqueca|reset system)\b",
        danger=1.0,
        category="adversarial",
        warning="Tentativa de hack! Resetando instruções.",
    ),
    TrapPattern(
        "roleplay_jailbreak",
        r"\b(DAN mode|developer mode|act as.*without restrictions)\b",
        danger=1.0,
        category="adversarial",
        warning="Jailbreak! Persona não autorizada.",
    ),
    # --- Hidden constraints ---
    TrapPattern(
        "false_premise",
        r"\b(assume 1\s*=\s*2|suponha que 1\s*=\s*2)\b",
        danger=0.8,
        category="logic_poisoning",
        warning="Premissa falsa! Rejeitar o problema.",
    ),
    # --- Financial fraud patterns ---
    TrapPattern(
        "guaranteed_return",
        r"\b(guaranteed|garantido|risk-free|sem risco|100% sure|cannot lose)\b",
        danger=1.0,
        category="fraud",
        warning="Retorno garantido é impossível. Possível fraude.",
    ),
    TrapPattern(
        "pump_and_dump",
        r"\b(pump\s*(and|&)\s*dump|10[xX]|100[xX]|1000[xX]|to the moon|moon shot)\b",
        danger=1.0,
        category="fraud",
        warning="Padrão clássico de pump and dump detectado.",
    ),
    TrapPattern(
        "insider_urgency",
        r"\b(buy (now|before)|don't miss|act (now|fast)|limited time|exclusive tip|inside(r)? info)\b",
        danger=0.9,
        category="fraud",
        warning="Urgência artificial — tática comum de manipulação.",
    ),
    TrapPattern(
        "penny_hype",
        r"\b(microcap|micro.cap|penny stock|OTC|pink sheet|sub.penny)\b",
        danger=0.5,
        category="fraud",
        warning="Penny stock / microcap — alta suscetibilidade a manipulação.",
    ),
    TrapPattern(
        "anonymous_source",
        r"\b(my (friend|buddy|guy)|telegram group|discord server|reddit.*said|someone told me)\b",
        danger=0.8,
        category="fraud",
        warning="Fonte anônima/não verificável — possível esquema de pump.",
    ),
    TrapPattern(
        "all_in_leverage",
        r"\b(all.in|yolo|full port|max leverage|mortgage|life savings)\b",
        danger=0.9,
        category="fraud",
        warning="Comportamento de risco extremo — possível vício em aposta.",
    ),
    TrapPattern(
        "promised_return",
        r"\b(\d{2,}[xX]\b|double.*money|triple.*money|\d+% return guaranteed|easy profit)\b",
        danger=0.8,
        category="fraud",
        warning="Promessa de retorno extraordinário — classic scam indicator.",
    ),
    TrapPattern(
        "ceo_manipulation",
        r"\b(CEO tweeted|CEO.*deleted|insider buying|buyback announced|merger rumors?)\b",
        danger=0.7,
        category="fraud",
        warning="Manipulação via anúncio corporativo não verificado.",
    ),
]


# =============================================================================
# SPIDER SENSE
# =============================================================================


@dataclass
class SpiderAlert:
    pattern: str
    category: str
    danger: float
    warning: str


class SpiderSense:
    """Detector de armadilhas. Não decide — só alerta."""

    def __init__(self, patterns: list[TrapPattern] | None = None):
        self.patterns = patterns or TRAP_PATTERNS
        self._compiled = [
            (p, re.compile(p.regex, re.IGNORECASE) if p.regex else None)
            for p in self.patterns
        ]

    def detect(self, text: str) -> tuple[float, list[SpiderAlert]]:
        """Analisa texto, retorna (danger_level, alerts)."""
        lower = text.lower()
        alerts: list[SpiderAlert] = []
        cumulative = 0.0
        critical = False

        for pattern, compiled in self._compiled:
            hit = False
            if compiled and compiled.search(text):
                hit = True
            elif pattern.keywords:
                hit = any(kw.lower() in lower for kw in pattern.keywords)

            if hit:
                alerts.append(
                    SpiderAlert(
                        pattern=pattern.name,
                        category=pattern.category,
                        danger=pattern.danger,
                        warning=pattern.warning,
                    )
                )
                if pattern.danger >= 1.0:
                    critical = True
                cumulative += pattern.danger

        if critical:
            danger = 1.0
        elif self.patterns:
            non_critical = sum(p.danger for p in self.patterns if p.danger < 1.0)
            danger = (
                1.0
                if non_critical == 0
                else min(1.0, cumulative / (non_critical * 0.25))
            )
        else:
            danger = 0.0

        return danger, alerts

    def get_config(self, danger: float) -> dict:
        """Pipeline adjustment based on danger level."""
        if danger < 0.3:
            return {
                "mode": "LIGHT",
                "n_candidates": 4,
                "temperature": 0.1,
                "verify_rounds": 1,
            }
        if danger < 0.7:
            return {
                "mode": "NORMAL",
                "n_candidates": 8,
                "temperature": 0.3,
                "verify_rounds": 2,
            }
        return {
            "mode": "PARANOID",
            "n_candidates": 16,
            "temperature": 0.5,
            "verify_rounds": 4,
        }


# =============================================================================
# DIFFICULTY ESTIMATOR
# =============================================================================


class DifficultyEstimator:
    """Estima dificuldade de um problema/input.

    Substitui o JEPA inteiro com heurística interpretável.
    """

    @staticmethod
    def estimate(text: str = "", features: dict[str, float] | None = None) -> float:
        return hu(text, features)

    def get_config(self, uncertainty: float) -> dict:
        if uncertainty < 0.3:
            return {"n_candidates": 2, "temperature": 0.1}
        if uncertainty < 0.6:
            return {"n_candidates": 4, "temperature": 0.3}
        return {"n_candidates": 8, "temperature": 0.5, "use_ensemble": True}
