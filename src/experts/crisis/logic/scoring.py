"""
Scoring and classification rules.
"""


def classify_alert_level(score: float) -> str:
    """Classify a canonical 0-1 risk score."""
    if not 0.0 <= score <= 1.0:
        raise ValueError("score must be on the unit interval [0, 1]")
    if score < 0.25:
        return "green"
    elif score < 0.50:
        return "yellow"
    elif score < 0.75:
        return "red"
    return "black"


def classify_regime(score: float, bubble_score: float, stress_score: float) -> str:
    """Classify unit-interval aggregate, bubble and stress scores."""
    values = (score, bubble_score, stress_score)
    if any(not 0.0 <= value <= 1.0 for value in values):
        raise ValueError("all regime scores must be on the unit interval [0, 1]")
    if stress_score >= 0.75 or (score >= 0.80 and stress_score >= 0.60):
        return "crisis"
    if stress_score >= 0.50 or (score >= 0.60 and bubble_score >= 0.50):
        return "stress"
    if bubble_score >= 0.60 or score >= 0.50:
        return "overheating"
    return "normal"
