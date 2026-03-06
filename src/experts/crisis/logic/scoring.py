"""
Scoring and classification rules.
"""


def classify_alert_level(score: float) -> str:
    if score < 25:
        return "green"
    elif score < 50:
        return "yellow"
    elif score < 75:
        return "red"
    return "black"


def classify_regime(score: float, bubble_score: float, stress_score: float) -> str:
    if stress_score >= 75 or (score >= 80 and stress_score >= 60):
        return "crisis"
    if stress_score >= 50 or (score >= 60 and bubble_score >= 50):
        return "stress"
    if bubble_score >= 60 or score >= 50:
        return "overheating"
    return "normal"
