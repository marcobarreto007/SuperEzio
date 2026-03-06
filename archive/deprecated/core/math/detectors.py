"""
F51 Detectors — SpiderSense e DifficultyEstimator.

Re-export do módulo canônico f51/detectors/__init__.py.
"""

from f51.detectors import (
    SpiderSense,
    SpiderAlert,
    DifficultyEstimator,
    TrapPattern,
)

__all__ = [
    "SpiderSense",
    "SpiderAlert",
    "DifficultyEstimator",
    "TrapPattern",
]
