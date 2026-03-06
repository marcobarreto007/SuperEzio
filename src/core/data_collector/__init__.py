"""Data Collector — agregador multi-fonte de dados financeiros."""

from .collector import DataCollector, detect_market
from .professional import ProfessionalCollector, get_professional_collector

__all__ = [
    "DataCollector",
    "ProfessionalCollector",
    "get_professional_collector",
    "detect_market",
]
