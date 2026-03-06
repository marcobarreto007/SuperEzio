"""Canonical response templates used across the pipeline.

Import from here rather than redefining locally.
"""

from __future__ import annotations

VAGUE_FINANCIAL_RESPONSE = (
    "I will not guess opportunities without concrete evidence.\n\n"
    "**STUDY_MORE**: To receive an analysis, you can:\n"
    "- Enter a specific ticker above, such as AAPL, GNS, or PETR4.SA\n"
    '- Ask for a scan with scope, such as: "scan Canadian penny stocks" '
    'or "find high-risk microcaps in tech"\n'
    "- Include a country or sector to trigger a market scan automatically\n\n"
    "Analysis without collected data can lead to a bad decision."
)
