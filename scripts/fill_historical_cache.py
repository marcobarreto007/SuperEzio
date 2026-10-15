"""Preenche o cache OHLCV (data/historical_cache.db) com o universo de taxa zero.

Por que existe
--------------
O cache tem cinco consumidores (``math_hub``, ``collector``,
``observation_builder``, ``batch_expert_runner``, ``bob_consciousness/body``) e
nenhum alimentador: ``fetch_and_cache_ticker``/``batch_fetch_universe`` existiam
sem caller desde que foram escritos, e por isso o HRP multi-ativo do ``math_hub``
nunca correu com dado (medido 2026-10-13: 0 linhas na tabela ``ohlcv_cache``).

Fontes, em ordem (ver ``historical_cache._load_candle_rows``):
  1. API chart do Yahoo por httpx (ajustado por splits/dividendos, 10 anos) — sem yfinance
  2. malha ajustada (``data_hub`` -> ``candle_history``, seis provedores)
  3. CSV as-traded do Coração (offline, sem chave)

O yfinance saiu do caminho: é um wrapper que quebra no seu próprio calendário
(um bump de versão trocou o nome de todas as colunas, medido no projeto do
comitê em 2026-10-13). O endpoint direto responde em ~0,4s por ticker.

Uso
---
    python scripts/fill_historical_cache.py                 # universo TD (133 símbolos)
    python scripts/fill_historical_cache.py RY.TO AAPL      # só estes
    python scripts/fill_historical_cache.py --force         # refaz a janela inteira
    python scripts/fill_historical_cache.py --max 20        # limita para teste

Idempotente: um ticker com mais de 50 candles no cache é pulado, portanto serve
para correr periodicamente sem custo de rede repetido.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.trading.historical_cache import (
    fetch_and_cache_ticker,
    get_cache_stats,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_FILE = ROOT / "config" / "td_direct_commission_free_etfs.json"


def yahoo_symbol(symbol: str, bucket: str) -> str:
    """Traduz o código do TD para o ticker do Yahoo.

    O universo do TD usa códigos sem sufixo (``FCID``, ``TGFI``, ``TGED-U``) e a
    listagem de classe com ponto (``BTCX.B``). O Yahoo exige ``FCID.TO``,
    ``TGED-U.TO`` e ``BTCX-B.TO`` — medido em 2026-10-13: sem a tradução, nenhum
    dos 83 canadenses resolve ("possibly delisted").
    """
    t = str(symbol).strip().upper()
    if t.endswith((".TO", ".V", ".CN")):
        return t
    dashed = t.replace(".", "-")  # classe: BTCX.B -> BTCX-B; BRK.B -> BRK-B
    if bucket == "CAN":
        return f"{dashed}.TO"
    return dashed


def carregar_universo() -> list[tuple[str, str]]:
    """Pares (código TD, ticker Yahoo) do universo commission-free, CAN + US + USA."""
    if not UNIVERSE_FILE.is_file():
        logger.warning("universo ausente: %s", UNIVERSE_FILE)
        return []
    payload = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    symbols = payload.get("symbols") or {}
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for bucket in ("CAN", "US", "USA"):
        for symbol in symbols.get(bucket) or []:
            item = str(symbol).strip().upper()
            if not item:
                continue
            ticker = yahoo_symbol(item, bucket)
            if ticker in seen:
                continue
            seen.add(ticker)
            ordered.append((item, ticker))
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enche o cache OHLCV do SuperEzio.")
    parser.add_argument("tickers", nargs="*", help="tickers Yahoo extra (senão, o universo TD)")
    parser.add_argument("--force", action="store_true", help="refaz mesmo quem já tem cache")
    parser.add_argument("--max", type=int, default=0, help="limita o número de tickers (0 = todos)")
    parser.add_argument("--quiet", action="store_true", help="só o resumo final")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if args.quiet:
        # O silêncio é do resumo, não da falha: o script imprime no fim quem não
        # carregou. Sem isto, cada símbolo falhado despeja 3 linhas de provider.
        for noisy in ("data.data_hub", "yfinance", "core.data_collector.candle_history"):
            logging.getLogger(noisy).setLevel(logging.ERROR)

    pares: list[tuple[str, str]] = [
        (t.strip().upper(), t.strip().upper()) for t in args.tickers if t.strip()
    ] or carregar_universo()
    if not pares:
        print("Nada para carregar: sem tickers e sem universo em config/.")
        return 1
    if args.max > 0:
        pares = pares[: args.max]

    antes = get_cache_stats()
    print(f"Cache antes: {antes['tickers_cached']} tickers, {antes['total_candles']} candles")
    print(f"Carregando {len(pares)} tickers...")

    vazios: list[str] = []
    total = 0
    for i, (codigo, ticker) in enumerate(pares, 1):
        count = fetch_and_cache_ticker(ticker, force=args.force)
        total += count
        if count == 0:
            vazios.append(codigo if codigo == ticker else f"{codigo}->{ticker}")
        if not args.quiet and i % 25 == 0:
            print(f"  {i}/{len(pares)}...")

    depois = get_cache_stats()
    print("--- resumo ---")
    print(f"candles gravados nesta corrida: {total}")
    print(
        f"cache agora: {depois['tickers_cached']} tickers, "
        f"{depois['total_candles']} candles "
        f"({depois['oldest_date']} -> {depois['newest_date']})"
    )
    if vazios:
        print(
            f"sem dados ({len(vazios)}): {', '.join(vazios[:20])}"
            + (" ..." if len(vazios) > 20 else "")
        )
    return 0 if depois["tickers_cached"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
