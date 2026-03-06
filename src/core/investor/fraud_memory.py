"""
FraudManipulationMemory — Base local de padrões de fraude e manipulação
========================================================================
Carrega e indexa os datasets locais:
  - data/fraud_patterns/fraud_patterns.json  : definições de padrões conhecidos
  - data/fraud_patterns/enforcement_cases.jsonl : casos seed com fonte
  - data/fraud_patterns/red_flag_rules.json  : regras de detecção computáveis

AVISO LEGAL:
  Este componente usa linguagem de "red flags" e "similarity to known patterns".
  NUNCA afirma fraude confirmada ou atividade ilegal.
  NUNCA acusa empresas específicas sem enforcement oficial citado.
"""

from __future__ import annotations

import threading as _threading

import json
from pathlib import Path
from typing import Any

from core.paths import project_path

# Localização padrão dos datasets — relativa à raiz do projeto
_DEFAULT_DATA_DIR = project_path("data", "fraud_patterns")


class FraudManipulationMemory:
    """
    Carrega e indexa padrões históricos de fraude/manipulação.

    Args:
        data_dir: Diretório com os três arquivos JSON/JSONL.
                  Padrão: data/fraud_patterns/ na raiz do projeto.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else _DEFAULT_DATA_DIR
        self._patterns: list[dict[str, Any]] = []
        self._rules: list[dict[str, Any]] = []
        self._cases: list[dict[str, Any]] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Carrega os três arquivos de dataset. Idempotente."""
        if self._loaded:
            return
        self._patterns = self._load_json("fraud_patterns.json").get("patterns", [])
        self._rules = self._load_json("red_flag_rules.json").get("rules", [])
        self._cases = self._load_jsonl("enforcement_cases.jsonl")
        self._loaded = True

    def get_patterns(self) -> list[dict[str, Any]]:
        """Retorna todas as definições de padrões."""
        self._ensure_loaded()
        return self._patterns

    def get_rules(self) -> list[dict[str, Any]]:
        """Retorna todas as regras de detecção."""
        self._ensure_loaded()
        return self._rules

    def get_computable_rules(self) -> list[dict[str, Any]]:
        """Regras que podem ser avaliadas com dados disponíveis (yfinance)."""
        self._ensure_loaded()
        return [r for r in self._rules if r.get("computable") is True]

    def get_non_computable_rules(self) -> list[dict[str, Any]]:
        """Regras que requerem providers não disponíveis (order book, insider data, etc.)."""
        self._ensure_loaded()
        return [r for r in self._rules if r.get("computable") is not True]

    def get_enforcement_cases(self) -> list[dict[str, Any]]:
        """Retorna todos os casos seed. Todos marcados como source='generic_pattern' no MVP."""
        self._ensure_loaded()
        return self._cases

    def get_enforcement_cases_by_types(
        self, case_types: list[str]
    ) -> list[dict[str, Any]]:
        """Filtra casos pelo tipo (pump_and_dump, spoofing, etc.)."""
        self._ensure_loaded()
        return [c for c in self._cases if c.get("case_type") in case_types]

    def find_patterns_by_ids(self, pattern_ids: list[str]) -> list[dict[str, Any]]:
        """Retorna definições completas de padrões pelo ID."""
        self._ensure_loaded()
        id_set = set(pattern_ids)
        return [p for p in self._patterns if p.get("pattern_id") in id_set]

    def get_rule_by_id(self, rule_id: str) -> dict[str, Any] | None:
        """Retorna uma regra pelo seu ID."""
        self._ensure_loaded()
        for rule in self._rules:
            if rule.get("rule_id") == rule_id:
                return rule
        return None

    def get_non_computable_limitations(self) -> list[str]:
        """Retorna as mensagens de limitação de todas as regras não computáveis."""
        self._ensure_loaded()
        return [
            r["limitation_when_absent"]
            for r in self.get_non_computable_rules()
            if r.get("limitation_when_absent")
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _load_json(self, filename: str) -> dict[str, Any]:
        path = self._data_dir / filename
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido em {path}: {exc}") from exc

    def _load_jsonl(self, filename: str) -> list[dict[str, Any]]:
        path = self._data_dir / filename
        records: list[dict[str, Any]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"JSONL inválido em {path} linha {line_num}: {exc}"
                        ) from exc
        except FileNotFoundError:
            return []
        return records


# Singleton para reutilização entre requests
_memory_instance: FraudManipulationMemory | None = None
_memory_lock: _threading.Lock = _threading.Lock()


def get_fraud_memory() -> FraudManipulationMemory:
    """Retorna singleton de FraudManipulationMemory (lazy-loaded, thread-safe)."""
    global _memory_instance
    if _memory_instance is None:
        with _memory_lock:
            if _memory_instance is None:
                _memory_instance = FraudManipulationMemory()
                _memory_instance.load()
    return _memory_instance
