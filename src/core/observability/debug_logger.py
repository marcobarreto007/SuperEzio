"""
DebugLogger — Sistema de Log de Depuração do SuperEzio
=======================================================
Wave 1: Caixa-preta que grava TUDO que acontece no pipeline.

Funcionalidades:
  - Níveis: TRACE / DEBUG / INFO / WARN / ERROR / FATAL
  - Flag global debug_enabled (ativa via env var SUPEREZIO_DEBUG)
  - Filtro por módulo (só loga módulos que interessam)
  - Buffer circular dos últimos N eventos para dumps
  - Callback integrado com neural_log.log_event
  - Timing automático (start/stop por módulo)
  - Serialização segura de objetos arbitrários

Uso:
    from ..observability import debug_logger

    debug_logger.info("committee", "Agent education started", ticker="AAPL")
    debug_logger.start_timer("data_collector.collect_all")
    # ... work ...
    elapsed = debug_logger.stop_timer("data_collector.collect_all")

    # Modo debug via env var:
    #   export SUPEREZIO_DEBUG=1          → debug ON
    #   export SUPEREZIO_DEBUG=module1,module2  → debug só pra esses módulos
    #   export SUPEREZIO_DEBUG=committee,data_collector  → filtrado
"""

from __future__ import annotations

import logging
import os
import time
import traceback
from collections import deque
from datetime import UTC, datetime
from typing import Any

# ── Module name constants ─────────────────────────────────────────────────
MODULE_COMMITTEE = "committee"
MODULE_CHAT = "chat"
MODULE_PIPELINE = "pipeline"
MODULE_SECURITY = "security"
MODULE_CACHE = "cache"
MODULE_DATA_COLLECTOR = "data_collector"
MODULE_VERACITY = "veracity_gate"
MODULE_MEMORY = "memory"
MODULE_TRACING = "tracing"
MODULE_INTENTS = "intents"
MODULE_DEBUGGER = "debugger"

# ── Level constants ───────────────────────────────────────────────────────
LEVEL_TRACE = 0
LEVEL_DEBUG = 1
LEVEL_INFO = 2
LEVEL_WARN = 3
LEVEL_ERROR = 4
LEVEL_FATAL = 5

LEVEL_NAMES = {
    LEVEL_TRACE: "TRACE",
    LEVEL_DEBUG: "DEBUG",
    LEVEL_INFO: "INFO",
    LEVEL_WARN: "WARN",
    LEVEL_ERROR: "ERROR",
    LEVEL_FATAL: "FATAL",
}

# ── Circular buffer size ──────────────────────────────────────────────────
DEFAULT_BUFFER_SIZE = 500


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _serialize(obj: Any) -> str:
    """Serializa qualquer objeto de forma segura para log."""
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialize(item) for item in obj]
    if obj is None:
        return None
    try:
        return str(obj)[:500]
    except Exception:
        return "<unserializable>"


class DebugLogger:
    """
    Logger de depuração global do SuperEzio.

    Attributes:
        debug_enabled: Flag global que ativa/desativa debug logging.
        module_filter: Se vazio, loga tudo. Se populado, só loga esses módulos.
        buffer: Deque circular com os últimos N eventos.
        _timers: Dict de timers ativos {name: start_time}.
    """

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE):
        self.debug_enabled = self._detect_debug_mode()
        self.module_filter: set[str] = self._detect_module_filter()
        self.buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._timers: dict[str, float] = {}
        self._event_count = 0
        self._error_count = 0
        self._neural_log_callback = None  # Será setado pelo pipeline

        if self.debug_enabled:
            self._log_internal(
                LEVEL_INFO,
                MODULE_DEBUGGER,
                "DebugLogger initialized",
                {
                    "buffer_size": buffer_size,
                    "module_filter": list(self.module_filter) or "ALL",
                },
            )

    # ── Public API ─────────────────────────────────────────────────────

    def trace(self, module: str, message: str, **kwargs) -> None:
        """Log TRACE level (detalhe extremamente fino)."""
        if self.debug_enabled and self._is_module_active(module):
            self._log_internal(LEVEL_TRACE, module, message, kwargs)

    def debug(self, module: str, message: str, **kwargs) -> None:
        """Log DEBUG level."""
        if self.debug_enabled and self._is_module_active(module):
            self._log_internal(LEVEL_DEBUG, module, message, kwargs)

    def info(self, module: str, message: str, **kwargs) -> None:
        """Log INFO level (logs mesmo sem debug ativo se module_filter passar)."""
        if self._is_module_active(module):
            self._log_internal(LEVEL_INFO, module, message, kwargs)

    def warn(self, module: str, message: str, **kwargs) -> None:
        """Log WARN level."""
        self._log_internal(LEVEL_WARN, module, message, kwargs)
        self._error_count += 1

    def error(self, module: str, message: str, **kwargs) -> None:
        """Log ERROR level com stack trace."""
        kwargs.setdefault("stack", traceback.format_exc(limit=5))
        self._log_internal(LEVEL_ERROR, module, message, kwargs)
        self._error_count += 1

    def fatal(self, module: str, message: str, **kwargs) -> None:
        """Log FATAL level (crítico, para debug sempre)."""
        kwargs.setdefault("stack", traceback.format_exc(limit=10))
        self._log_internal(LEVEL_FATAL, module, message, kwargs)
        self._error_count += 1

    # ── Timing ─────────────────────────────────────────────────────────

    def start_timer(self, label: str) -> None:
        """Inicia cronômetro com label."""
        self._timers[label] = time.time()
        self.trace(MODULE_DEBUGGER, f"Timer started: {label}")

    def stop_timer(self, label: str) -> float:
        """
        Para cronômetro e retorna duração em ms.
        Se o timer não existir, retorna 0.0.
        """
        started = self._timers.pop(label, None)
        if started is None:
            self.warn(
                MODULE_DEBUGGER,
                f"Timer '{label}' not found — never started or already stopped",
            )
            return 0.0
        elapsed_ms = (time.time() - started) * 1000.0
        self.debug(MODULE_DEBUGGER, f"Timer ended: {label}", elapsed_ms=round(elapsed_ms, 2))
        return elapsed_ms

    def elapsed_since(self, label: str) -> float | None:
        """Retorna ms desde o início do timer sem pará-lo."""
        started = self._timers.get(label)
        if started is None:
            return None
        return (time.time() - started) * 1000.0

    # ── Buffer operations ──────────────────────────────────────────────

    def get_recent_events(
        self, n: int = 50, module: str | None = None, level: int | None = None
    ) -> list[dict[str, Any]]:
        """Retorna os últimos N eventos, opcionalmente filtrados."""
        events = list(self.buffer)
        if module:
            events = [e for e in events if e.get("module") == module]
        if level is not None:
            events = [e for e in events if e.get("level") >= level]
        return events[-n:]

    def get_errors(self, n: int = 20) -> list[dict[str, Any]]:
        """Retorna os últimos N eventos de erro."""
        return self.get_recent_events(n=n, level=LEVEL_WARN)

    def get_module_summary(self) -> dict[str, Any]:
        """Gera resumo de logs por módulo."""
        summary: dict[str, dict[str, int]] = {}
        for event in self.buffer:
            mod = event.get("module", "unknown")
            lvl = event.get("level", LEVEL_INFO)
            if mod not in summary:
                summary[mod] = {
                    "trace": 0,
                    "debug": 0,
                    "info": 0,
                    "warn": 0,
                    "error": 0,
                    "fatal": 0,
                }
            lvl_name = LEVEL_NAMES.get(lvl, "info").lower()
            if lvl_name in summary[mod]:
                summary[mod][lvl_name] += 1
        return summary

    def dump_all(self) -> dict[str, Any]:
        """Dump completo do estado do DebugLogger."""
        return {
            "debug_enabled": self.debug_enabled,
            "module_filter": list(self.module_filter) if self.module_filter else "ALL",
            "buffer_size": self.buffer.maxlen,
            "event_count": self._event_count,
            "error_count": self._error_count,
            "active_timers": list(self._timers.keys()),
            "module_summary": self.get_module_summary(),
        }

    def clear_buffer(self) -> None:
        """Limpa o buffer de eventos."""
        self.buffer.clear()
        self._event_count = 0
        self._error_count = 0
        self.info(MODULE_DEBUGGER, "Debug buffer cleared")

    # ── Toggle debug mode at runtime ───────────────────────────────────

    def enable(self) -> None:
        """Ativa debug mode em runtime."""
        self.debug_enabled = True
        self.info(MODULE_DEBUGGER, "Debug mode ENABLED at runtime")

    def disable(self) -> None:
        """Desativa debug mode em runtime."""
        self.debug_enabled = False
        self._log_internal(LEVEL_INFO, MODULE_DEBUGGER, "Debug mode DISABLED at runtime", {})

    def set_module_filter(self, modules: list[str]) -> None:
        """Define filtro de módulos para debug."""
        self.module_filter = set(modules)
        self.info(MODULE_DEBUGGER, "Module filter updated", modules=modules)

    def clear_module_filter(self) -> None:
        """Remove filtro de módulos (loga tudo)."""
        self.module_filter = set()
        self.info(MODULE_DEBUGGER, "Module filter cleared — logging ALL modules")

    # ── Internal ───────────────────────────────────────────────────────

    def _log_internal(
        self, level: int, module: str, message: str, data: dict | None = None
    ) -> None:
        """Registra um evento no buffer."""
        event = {
            "timestamp": _now_iso(),
            "level": level,
            "level_name": LEVEL_NAMES.get(level, "UNKNOWN"),
            "module": module,
            "message": message,
            "data": _serialize(data or {}),
        }
        self.buffer.append(event)
        self._event_count += 1

        # Callback para neural_log se configurado
        if self._neural_log_callback:
            try:
                self._neural_log_callback(
                    f"DEBUG_{module.upper()}", event["level_name"], event["data"]
                )
            except Exception:
                pass  # Não quebrar por causa de callback de log

        # Console output (só em debug mode ou errors)
        if self.debug_enabled or level >= LEVEL_WARN:
            prefix = f"[DEBUG:{module.upper()}]" if level <= LEVEL_DEBUG else f"[{module.upper()}]"
            logging.getLogger("F51-DEBUG").log(
                level, "%s [%s] %s", prefix, LEVEL_NAMES.get(level, "?"), message
            )

    def _is_module_active(self, module: str) -> bool:
        """Verifica se o módulo deve ser logado baseado no filtro."""
        if not self.module_filter:
            return True
        return module in self.module_filter

    @staticmethod
    def _detect_debug_mode() -> bool:
        """Detecta se debug deve ser ativo baseado em env var."""
        env_val = os.environ.get("SUPEREZIO_DEBUG", "").strip()
        if env_val == "0" or env_val.lower() == "false":
            return False
        return bool(env_val)

    @staticmethod
    def _detect_module_filter() -> set[str]:
        """Detecta filtro de módulos do env var SUPEREZIO_DEBUG."""
        env_val = os.environ.get("SUPEREZIO_DEBUG", "").strip()
        if not env_val or env_val == "1" or env_val.lower() == "true":
            return set()  # All modules
        return {m.strip() for m in env_val.split(",") if m.strip()}

    def set_neural_log_callback(self, callback):
        """Define callback para integração com neural_log.log_event."""
        self._neural_log_callback = callback


# ── Global singleton ──────────────────────────────────────────────────────
debug_logger = DebugLogger()
