"""Health probe via HTTP GET (requests)."""

from __future__ import annotations

import requests

from core.ports.health_probe import HealthProbePort


class HttpProbe(HealthProbePort):
    """Verifica disponibilidade de um endpoint HTTP."""

    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout
        self._session = requests.Session()
        self._session.trust_env = False  # skip system proxy

    async def is_ready(self, base_url: str) -> bool:
        if not base_url:
            return False

        normalized = base_url.rstrip("/")
        candidates = [
            f"{normalized}/models",
            f"{normalized}/health",
        ]

        if not normalized.endswith("/v1"):
            candidates.append(f"{normalized}/v1/models")
        if "/v1" in normalized:
            root = normalized.split("/v1", 1)[0]
            candidates.extend([f"{root}/health", f"{root}/v1/models"])

        # remove duplicados mantendo ordem
        seen = set()
        ordered_candidates = []
        for url in candidates:
            if url not in seen:
                seen.add(url)
                ordered_candidates.append(url)

        for url in ordered_candidates:
            try:
                response = self._session.get(
                    url,
                    headers={"User-Agent": "SuperEzio-HealthProbe/1.0"},
                    timeout=self.timeout,
                )
                if response.status_code < 500:
                    return True
            except Exception:
                continue

        return False
