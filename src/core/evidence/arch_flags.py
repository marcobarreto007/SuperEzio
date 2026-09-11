"""Architecture-cut flags.

Live toggle is the process environment so tests and operators can flip a cut
without fighting the import-time Settings singleton. Defaults MUST match the
Settings fields of the same name.
"""

from __future__ import annotations

import os

_FALSE = frozenset({"0", "false", "no", "off"})
_TRUE = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    token = str(raw).strip().lower()
    if token in _FALSE:
        return False
    if token in _TRUE:
        return True
    return default


def is_arch_c1_enabled() -> bool:
    """C1 default ON (shadow pack write). SUPEREZIO_ARCH_C1=0 rolls back."""
    return env_flag("SUPEREZIO_ARCH_C1", default=True)


def is_arch_c2_enabled() -> bool:
    """C2 default ON (shadow snapshot freeze). SUPEREZIO_ARCH_C2=0 rolls back.

    Freeze + disk only. Prompt bind is C3.
    """
    return env_flag("SUPEREZIO_ARCH_C2", default=True)


def is_arch_c3_enabled() -> bool:
    """C3 default ON (bind Bob to snapshot). SUPEREZIO_ARCH_C3=0 rolls back."""
    return env_flag("SUPEREZIO_ARCH_C3", default=True)


def is_arch_c4_enabled() -> bool:
    """C4 default OFF (observe). SUPEREZIO_ARCH_C4=1 enforces the SDCA edge."""
    return env_flag("SUPEREZIO_ARCH_C4", default=False)
