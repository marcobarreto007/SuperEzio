"""Configuracao do bridge. Nada aqui le .env — so ambiente do processo e os .toml locais.

`bridge/events.toml` e o inventario canonico das rotas do Ezio (entregue pela
Fase 2 e lido pelo teste dela). O bridge NAO escreve nesse arquivo: ele o le.
Fonte unica de verdade evita o risco §9 do plano — duas listas que divergem em
silencio.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BRIDGE_DIR = Path(__file__).resolve().parent

# Bind: constante, nao configuravel. O bridge nunca vai atras de tunel.
HOST = "127.0.0.1"
DEFAULT_PORT = 8009

DEFAULT_EZIO_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_MIKE_BASE_URL = "http://127.0.0.1:8083"

# Contrato de comando da Fase 2 (events.toml [commands] route). Assumido e
# configuravel: se a rota nao existir no Ezio, o bridge devolve 503 e nao inventa.
DEFAULT_COMMAND_PATH = "/control/commands"

# Canal de publicacao no MIKE: rota que JA existe (autonomy.py:829).
MIKE_SEND_PATH = "/v1/notifications/send"

DEFAULT_POLL_INTERVAL_S = 5.0
DEFAULT_HTTP_TIMEOUT_S = 5.0
DEFAULT_COMMAND_TIMEOUT_S = 10.0

# Rotas cujo corpo e uma lista de itens (o diff reporta os novos item a item).
LIST_MODE_PATHS = {"/trades/history", "/sentiment/alerts"}

# Parametros de query exigidos pela spec da Fase 3 (§2: /trades/history?limit=50).
DEFAULT_PARAMS_BY_PATH: dict[str, dict[str, str]] = {"/trades/history": {"limit": "50"}}

# Vocabulario de eventos de ciclo de vida (events.toml [events]).
DEFAULT_VOCABULARY = {
    "boot": "ezio.boot",
    "restarted": "ezio.restarted",
    "degraded": "ezio.degraded",
    "recovered": "ezio.recovered",
    "command_settled": "ezio.command.settled",
    "command_denied": "ezio.command.denied",
}

LIFECYCLE_EVENTS = frozenset({"ezio.boot", "ezio.restarted", "ezio.degraded", "ezio.recovered"})


def env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def env_float(name: str, default: float) -> float:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    raw = env_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class PollRoute:
    """Uma rota do Ezio coletada por polling.

    event_type vazio => rota somente de ciclo de vida (ex.: /health alimenta
    ezio.degraded/ezio.recovered/ezio.restarted e nao tem evento proprio).
    """

    path: str
    event_type: str = ""
    mode: str = "state"  # "state" (hash do corpo) | "list" (itens novos)
    params: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.event_type or self.path


@dataclass(frozen=True)
class CommandSpec:
    """Um `kind` permitido e o alvo dele no Ezio."""

    kind: str
    path: str
    method: str = "POST"
    enabled: bool = True


@dataclass
class Settings:
    ezio_base_url: str = DEFAULT_EZIO_BASE_URL
    mike_base_url: str = DEFAULT_MIKE_BASE_URL
    port: int = DEFAULT_PORT
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S
    http_timeout_s: float = DEFAULT_HTTP_TIMEOUT_S
    command_timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S
    command_path: str = DEFAULT_COMMAND_PATH
    mike_send_path: str = MIKE_SEND_PATH
    routes: list[PollRoute] = field(default_factory=list)
    commands: dict[str, CommandSpec] = field(default_factory=dict)
    # Todas as rotas declaradas no inventario ("GET /x" -> entrada crua).
    inventory: dict[str, Any] = field(default_factory=dict)
    vocabulary: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VOCABULARY))
    config_errors: list[str] = field(default_factory=list)

    def is_declared(self, method: str, route_path: str) -> bool:
        """A rota esta no inventario do events.toml?"""
        return f"{method.upper()} {route_path}" in self.inventory

    def snapshot_paths(self) -> list[str]:
        return [route.path for route in self.routes]


def _load_toml(path: Path, errors: list[str] | None = None) -> dict[str, Any]:
    if not path.exists():
        if errors is not None:
            errors.append(f"arquivo ausente: {path.name}")
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        if errors is not None:
            errors.append(f"{path.name} ilegivel: {exc}")
        return {}


def _split_route_key(key: str) -> tuple[str, str] | None:
    parts = key.split(" ", 1)
    if len(parts) != 2 or not parts[1].startswith("/"):
        return None
    return parts[0].upper(), parts[1].strip()


def _change_event(emits: list[Any]) -> str:
    """Primeiro evento do `emits` que nao seja de ciclo de vida."""
    for name in emits:
        text = str(name)
        if text not in LIFECYCLE_EVENTS:
            return text
    return ""


def load_poll_routes(
    data: dict[str, Any] | None = None, errors: list[str] | None = None
) -> list[PollRoute]:
    """Rotas coletadas = entradas do inventario com snapshot = true (em ordem de arquivo)."""
    errors = [] if errors is None else errors
    data = _load_toml(BRIDGE_DIR / "events.toml", errors) if data is None else data
    routes: list[PollRoute] = []

    # Schema do inventario (Fase 2): [routes] "METHOD /path" = { snapshot = true, ... }
    for key, entry in data.get("routes", {}).items():
        if not isinstance(entry, dict) or not entry.get("snapshot"):
            continue
        parsed = _split_route_key(str(key))
        if parsed is None:
            errors.append(f"chave de rota invalida: {key!r}")
            continue
        method, route_path = parsed
        if method != "GET":
            continue
        mode = str(entry.get("mode") or ("list" if route_path in LIST_MODE_PATHS else "state"))
        params = {str(k): str(v) for k, v in dict(entry.get("params", {})).items()}
        if not params:
            params = dict(DEFAULT_PARAMS_BY_PATH.get(route_path, {}))
        routes.append(
            PollRoute(
                path=route_path,
                event_type=_change_event(list(entry.get("emits", []))),
                mode=mode,
                params=params,
            )
        )

    # Schema antigo/standalone: [[poll]] (mantido para nao quebrar config propria).
    for entry in data.get("poll", []):
        route_path = str(entry.get("path", "")).strip()
        if not route_path:
            errors.append(f"evento de poll incompleto: {entry!r}")
            continue
        routes.append(
            PollRoute(
                path=route_path,
                event_type=str(entry.get("event_type", "")).strip(),
                mode=str(entry.get("mode", "state")),
                params={str(k): str(v) for k, v in dict(entry.get("params", {})).items()},
            )
        )

    if not routes:
        errors.append("nenhuma rota de polling declarada em events.toml (snapshot = true)")
    return routes


def load_commands(
    data: dict[str, Any] | None = None, errors: list[str] | None = None
) -> dict[str, CommandSpec]:
    """Allowlist de comandos. Sem inventario legivel => allowlist VAZIA (default-deny)."""
    errors = [] if errors is None else errors
    data = _load_toml(BRIDGE_DIR / "events.toml", errors) if data is None else data
    block = dict(data.get("commands", {}))
    route = str(block.get("route", f"POST {DEFAULT_COMMAND_PATH}")).strip()
    parsed = _split_route_key(route) or ("POST", DEFAULT_COMMAND_PATH)
    method, route_path = parsed
    specs: dict[str, CommandSpec] = {}
    for kind in block.get("allowed", []):
        name = str(kind).strip()
        if not name:
            continue
        specs[name] = CommandSpec(kind=name, path=route_path, method=method)
    # Overrides explicitos, se alguem preferir declarar aqui.
    for entry in block.get("command", []):
        name = str(dict(entry).get("kind", "")).strip()
        if not name:
            continue
        specs[name] = CommandSpec(
            kind=name,
            path=str(dict(entry).get("path", route_path)),
            method=str(dict(entry).get("method", method)).upper(),
            enabled=bool(dict(entry).get("enabled", True)),
        )
    if not specs:
        errors.append("allowlist de comandos vazia: todo kind sera 403")
    return specs


def load_vocabulary(
    data: dict[str, Any] | None = None, errors: list[str] | None = None
) -> dict[str, str]:
    """Nomes de evento do inventario; divergencia vira config_error (nao quebra)."""
    errors = [] if errors is None else errors
    data = _load_toml(BRIDGE_DIR / "events.toml", None) if data is None else data
    declared = set(data.get("events", {}))
    vocabulary = dict(DEFAULT_VOCABULARY)
    if declared:
        for name in DEFAULT_VOCABULARY.values():
            if name not in declared:
                errors.append(f"evento {name} nao esta no vocabulario de events.toml")
    return vocabulary


def load_settings() -> Settings:
    errors: list[str] = []
    data = _load_toml(BRIDGE_DIR / "events.toml", errors)
    routes = load_poll_routes(data, errors)
    commands = load_commands(data, errors)
    vocabulary = load_vocabulary(data, errors)
    meta = dict(data.get("meta", {}))
    return Settings(
        ezio_base_url=env_str("BRIDGE_EZIO_BASE_URL", DEFAULT_EZIO_BASE_URL).rstrip("/"),
        mike_base_url=env_str("BRIDGE_MIKE_BASE_URL", DEFAULT_MIKE_BASE_URL).rstrip("/"),
        port=env_int("BRIDGE_PORT", DEFAULT_PORT),
        poll_interval_s=env_float(
            "BRIDGE_POLL_INTERVAL_S",
            float(meta.get("snapshot_poll_interval_s", DEFAULT_POLL_INTERVAL_S)),
        ),
        http_timeout_s=env_float("BRIDGE_HTTP_TIMEOUT_S", DEFAULT_HTTP_TIMEOUT_S),
        command_timeout_s=env_float("BRIDGE_COMMAND_TIMEOUT_S", DEFAULT_COMMAND_TIMEOUT_S),
        command_path=env_str(
            "BRIDGE_EZIO_COMMAND_PATH",
            next(iter({spec.path for spec in commands.values()}), DEFAULT_COMMAND_PATH),
        ),
        routes=routes,
        commands=commands,
        inventory=dict(data.get("routes", {})),
        vocabulary=vocabulary,
        config_errors=errors,
    )
