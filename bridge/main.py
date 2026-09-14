"""Entrypoint: uvicorn em 127.0.0.1:8009.

O bind e loopback por construcao. Se alguem tentar outro host, o processo morre
antes de abrir o socket.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from bridge import __version__
from bridge.config import HOST, load_settings


def main() -> int:
    settings = load_settings()
    if HOST != "127.0.0.1":
        print("bridge recusa bind fora de loopback", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger(__name__).info(
        "bridge %s em http://%s:%s (ezio=%s, mike=%s)",
        __version__,
        HOST,
        settings.port,
        settings.ezio_base_url,
        settings.mike_base_url,
    )
    for problem in settings.config_errors:
        logging.getLogger(__name__).warning("config: %s", problem)

    uvicorn.run(
        "bridge.app:app",
        host=HOST,
        port=settings.port,
        log_level="info",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
