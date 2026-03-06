import json
import logging
import os
from typing import Any, List

import pandas as pd

from core.paths import resolve_project_path

logger = logging.getLogger(__name__)


class FraudRAG:
    """
    Forensic RAG for fraud, scams, insider trading, and pump-and-dump patterns.
    """

    def __init__(self, data_dir: str = "data/fraud_patterns"):
        self.data_dir = str(resolve_project_path(data_dir))
        self.knowledge_base = []
        self.pump_symbols = set()
        self._load_data()

    def _load_data(self):
        if not os.path.exists(self.data_dir):
            return

        files = os.listdir(self.data_dir)
        for f in files:
            try:
                full_path = os.path.join(self.data_dir, f)
                if f.endswith(".json"):
                    self._load_json_patterns(full_path)
                    continue
                if f.endswith(".jsonl"):
                    self._load_jsonl_patterns(full_path)
                    continue
                if not f.endswith(".parquet"):
                    continue

                df = pd.read_parquet(full_path)

                if "pump_dump" in f:
                    if "symbol" in df.columns:
                        self.pump_symbols.update(df["symbol"].unique().tolist())
                    continue

                if "sentence" in df.columns:
                    texts = df[df["label"] == 1]["sentence"].tolist()
                elif "text" in df.columns:
                    texts = df["text"].tolist()
                else:
                    texts = df.select_dtypes(include=["object"]).iloc[:, 0].tolist()

                self.knowledge_base.extend([str(t) for t in texts])
            except (
                FileNotFoundError,
                json.JSONDecodeError,
                OSError,
                pd.errors.EmptyDataError,
                ValueError,
            ):
                pass

        logger.info(
            "FraudRAG: loaded %d text patterns and %d pump symbols.",
            len(self.knowledge_base),
            len(self.pump_symbols),
        )

    def _add_pattern_text(self, value: Any):
        text = str(value or "").strip()
        if text and text not in self.knowledge_base:
            self.knowledge_base.append(text)

    def _load_json_patterns(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, dict):
            return

        for pattern in payload.get("patterns", []):
            if not isinstance(pattern, dict):
                continue
            parts = [
                pattern.get("name"),
                pattern.get("description"),
                " ".join(pattern.get("typical_red_flags") or []),
                " ".join(pattern.get("regulatory_references") or []),
            ]
            self._add_pattern_text(" | ".join(str(p) for p in parts if p))

        for rule in payload.get("rules", []):
            if not isinstance(rule, dict):
                continue
            parts = [
                rule.get("name"),
                rule.get("description"),
                rule.get("condition"),
                " ".join(rule.get("matched_patterns") or []),
                rule.get("note"),
            ]
            self._add_pattern_text(" | ".join(str(p) for p in parts if p))

    def _load_jsonl_patterns(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                parts = [
                    row.get("case_type"),
                    row.get("summary"),
                    " ".join(row.get("known_red_flags") or []),
                    row.get("notes"),
                ]
                self._add_pattern_text(" | ".join(str(p) for p in parts if p))

    def search_patterns(self, query: str, limit: int = 3) -> List[str]:
        results = []
        query_lower = query.lower()

        if query.upper() in self.pump_symbols:
            results.append(
                f"[TECHNICAL_ALERT]: {query.upper()} has historical Pump & Dump manipulation markers in the forensic logs."
            )

        keywords = [k for k in query_lower.replace(",", " ").split() if len(k) > 3]
        if self.knowledge_base and keywords:
            for text in self.knowledge_base:
                score = sum(1 for kw in keywords if kw in text.lower())
                if score > 0:
                    results.append("[PATTERN_FOUND]: " + text[:800] + "...")

        results.sort(key=lambda x: len(x), reverse=True)
        return results[:limit]


fraud_rag = FraudRAG()
