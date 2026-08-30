"""Chart evidence for the local mouth.

Default path is text-only: the same OHLCV facts the pipeline already has.
PNG attach is opt-in (`attach_image=True`) for the retired vision mouth.
Fail closed when candles are missing or short.
"""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

MIN_CANDLES = 20
CHART_WIDTH = 960
CHART_HEIGHT = 480
_PAD_L = 48
_PAD_R = 16
_PAD_T = 36
_PAD_B = 56  # volume pane

# Tiny 5x7 glyphs for the header (A-Z, 0-9, .:-$). Enough for ticker + price.
_FONT: dict[str, tuple[str, ...]] = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "$": ("01110", "10101", "10100", "01110", "00101", "10101", "01110"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00110", "01000", "10000", "11111"),
    "3": ("01110", "10001", "00001", "00110", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("01110", "10000", "11110", "10001", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
}


def extract_ohlcv(state: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Return (ticker, candles) from pipeline state. Empty candles if missing."""
    ticker = str(state.get("ticker") or "").strip().upper()
    data = state.get("data") if isinstance(state.get("data"), dict) else {}
    candles = _as_candle_list(data.get("ohlcv") or data.get("candles"))
    if not ticker:
        ticker = str(data.get("ticker") or data.get("symbol") or "").strip().upper()
    if candles:
        return ticker, candles

    scan = state.get("scan") if isinstance(state.get("scan"), dict) else {}
    candidates = scan.get("candidates") or scan.get("results") or []
    if isinstance(candidates, list):
        for item in candidates:
            if not isinstance(item, dict):
                continue
            nested = _as_candle_list(item.get("ohlcv") or item.get("candles"))
            if nested:
                return str(item.get("ticker") or item.get("symbol") or ticker).upper(), nested
    return ticker, []


def _as_candle_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            high = float(row.get("high", row.get("h")))
            low = float(row.get("low", row.get("l")))
            open_ = float(row.get("open", row.get("o", row.get("close", row.get("c")))))
            close = float(row.get("close", row.get("c")))
        except (TypeError, ValueError):
            continue
        if high <= 0 or low <= 0 or close <= 0:
            continue
        volume = row.get("volume", row.get("v", 0)) or 0
        try:
            volume_f = float(volume)
        except (TypeError, ValueError):
            volume_f = 0.0
        out.append(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume_f,
            }
        )
    return out


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def chart_facts(ticker: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [c["close"] for c in candles]
    last = candles[-1]
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    trend = "insuficiente"
    if sma20 is not None:
        if last["close"] > sma20:
            trend = "preco acima da SMA20"
        elif last["close"] < sma20:
            trend = "preco abaixo da SMA20"
        else:
            trend = "preco na SMA20"
    return {
        "ticker": ticker,
        "candles": len(candles),
        "last_close": round(last["close"], 4),
        "last_volume": last["volume"],
        "sma20": None if sma20 is None else round(sma20, 4),
        "sma50": None if sma50 is None else round(sma50, 4),
        "trend": trend,
        "range_high": round(max(c["high"] for c in candles), 4),
        "range_low": round(min(c["low"] for c in candles), 4),
    }


def render_ohlcv_png(ticker: str, candles: list[dict[str, Any]]) -> bytes:
    """Deterministic RGB PNG. Raises ValueError when the series is too short."""
    if len(candles) < MIN_CANDLES:
        raise ValueError(f"need_at_least_{MIN_CANDLES}_candles")
    w, h = CHART_WIDTH, CHART_HEIGHT
    buf = bytearray([18, 22, 28]) * (w * h)

    def put(x: int, y: int, rgb: tuple[int, int, int]) -> None:
        if 0 <= x < w and 0 <= y < h:
            i = (y * w + x) * 3
            buf[i : i + 3] = bytes(rgb)

    def hline(x0: int, x1: int, y: int, rgb: tuple[int, int, int]) -> None:
        if x1 < x0:
            x0, x1 = x1, x0
        for x in range(x0, x1 + 1):
            put(x, y, rgb)

    def vline(x: int, y0: int, y1: int, rgb: tuple[int, int, int]) -> None:
        if y1 < y0:
            y0, y1 = y1, y0
        for y in range(y0, y1 + 1):
            put(x, y, rgb)

    def text(x: int, y: int, s: str, rgb: tuple[int, int, int], scale: int = 2) -> None:
        cx = x
        for ch in s.upper():
            glyph = _FONT.get(ch, _FONT[" "])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit != "1":
                        continue
                    for dy in range(scale):
                        for dx in range(scale):
                            put(cx + gx * scale + dx, y + gy * scale + dy, rgb)
            cx += 6 * scale

    price_top = _PAD_T
    price_bot = h - _PAD_B
    vol_top = h - _PAD_B + 8
    vol_bot = h - 8
    plot_left = _PAD_L
    plot_right = w - _PAD_R
    plot_w = max(1, plot_right - plot_left)
    n = len(candles)
    px = plot_w / n

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    pmin, pmax = min(lows), max(highs)
    if pmax <= pmin:
        pmax = pmin + 1e-6
    vmax = max((c["volume"] for c in candles), default=1.0) or 1.0

    def y_price(v: float) -> int:
        t = (v - pmin) / (pmax - pmin)
        return int(price_bot - t * (price_bot - price_top))

    def y_vol(v: float) -> int:
        t = min(1.0, v / vmax)
        return int(vol_bot - t * (vol_bot - vol_top))

    grid = (40, 48, 58)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = int(price_bot - frac * (price_bot - price_top))
        hline(plot_left, plot_right, y, grid)

    closes = [c["close"] for c in candles]
    sma20 = _sma(closes, 20)
    up = (46, 204, 113)
    down = (231, 76, 60)
    wick = (180, 186, 194)
    vol_up = (32, 140, 80)
    vol_down = (150, 50, 50)
    sma_color = (80, 180, 255)

    body_w = max(1, int(px * 0.6))
    for i, c in enumerate(candles):
        x = plot_left + int((i + 0.5) * px)
        y_h, y_l = y_price(c["high"]), y_price(c["low"])
        y_o, y_c = y_price(c["open"]), y_price(c["close"])
        color = up if c["close"] >= c["open"] else down
        vline(x, y_h, y_l, wick)
        top, bot = (y_c, y_o) if y_c < y_o else (y_o, y_c)
        if top == bot:
            hline(x - body_w // 2, x + body_w // 2, top, color)
        else:
            for yy in range(top, bot + 1):
                hline(x - body_w // 2, x + body_w // 2, yy, color)
        vy0, vy1 = y_vol(c["volume"]), vol_bot
        vcolor = vol_up if c["close"] >= c["open"] else vol_down
        for yy in range(vy0, vy1 + 1):
            hline(x - max(1, body_w // 2), x + max(1, body_w // 2), yy, vcolor)

    if sma20 is not None and n >= 20:
        prev: tuple[int, int] | None = None
        for i in range(19, n):
            val = sum(closes[i - 19 : i + 1]) / 20.0
            pt = (plot_left + int((i + 0.5) * px), y_price(val))
            if prev is not None:
                x0, y0 = prev
                x1, y1 = pt
                steps = max(abs(x1 - x0), abs(y1 - y0), 1)
                for s in range(steps + 1):
                    put(x0 + (x1 - x0) * s // steps, y0 + (y1 - y0) * s // steps, sma_color)
                    put(x0 + (x1 - x0) * s // steps, y0 + (y1 - y0) * s // steps + 1, sma_color)
            prev = pt

    facts = chart_facts(ticker, candles)
    sma_txt = "NA" if facts["sma20"] is None else str(facts["sma20"])
    header = f"{ticker} CLOSE {facts['last_close']} SMA20 {sma_txt} N={n}"
    text(8, 8, header[:78], (230, 230, 230))
    text(8, h - 7, "GREEN UP  RED DOWN  BLUE SMA20  BARS VOLUME", (140, 148, 160))
    return _png_rgb(w, h, bytes(buf))


def _png_rgb(width: int, height: int, rgb: bytes) -> bytes:
    if len(rgb) != width * height * 3:
        raise ValueError("rgb_buffer_size_mismatch")

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride : (y + 1) * stride])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def png_data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def evidence_contract_text(facts: dict[str, Any], has_chart: bool) -> str:
    """Binding instruction: buy only from chart + pipeline evidence."""
    if not has_chart:
        return (
            "CONTRATO FAIL-CLOSED: nao ha velas reais o bastante para gerar o grafico. "
            "Nao recomende COMPRA. Diga WAIT. Explique o que falta "
            "(serie OHLCV do DataHub). Nao invente padrao visual nem catalisador."
        )
    return (
        "GRAFICO REAL ANEXADO (velas do DataHub, mesma serie do MathHub). "
        f"Ticker={facts.get('ticker')} close={facts.get('last_close')} "
        f"SMA20={facts.get('sma20')} tendencia={facts.get('trend')} "
        f"n={facts.get('candles')} volume_ultima={facts.get('last_volume')}.\n"
        "CONTRATO DE EVIDENCIA (obrigatorio):\n"
        "1. Descreva o que o GRAFICO mostra: tendencia, ultima vela vs SMA20 (linha azul), volume.\n"
        "2. Cruze com os numeros EXATOS do pipeline (RSI, MACD, F51, SDCA). Sem arredondar de cabeca.\n"
        "3. So diga COMPRAR se as tres pecas existirem: catalisador concreto no pipeline, "
        "grafico confirmando (preco vs SMA/rompimento com volume), e F51/SDCA nao BLOCK.\n"
        "4. Se faltar qualquer peca: WAIT. Nao invente motivo de compra.\n"
        "5. Estrutura: PORQUE (evidencia visual + quantitativa), RISCO, INVALIDACAO, ACAO "
        "(WAIT ou PAPER apenas). Live continua congelado."
    )


def build_chart_visual_message(
    state: dict[str, Any], *, attach_image: bool = False
) -> dict[str, Any] | None:
    """User message with chart facts, or a fail-closed text notice.

    Returns None when the turn is not a ticker/trade case (no hollow chart leak).
    Local mouth (Ornith) is text-only — PNG is not attached unless attach_image.
    """
    ticker, candles = extract_ohlcv(state)
    needs_chart = bool(ticker) or bool(state.get("ticker_allowed"))
    if not needs_chart:
        return None

    if len(candles) < MIN_CANDLES:
        return {"role": "user", "content": evidence_contract_text({}, False)}

    facts = chart_facts(ticker or "UNKNOWN", candles)
    caption = evidence_contract_text(facts, True)
    if not attach_image:
        return {"role": "user", "content": caption, "_chart_facts": facts}

    png = render_ohlcv_png(ticker or "UNKNOWN", candles)
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": caption},
            {"type": "image_url", "image_url": {"url": png_data_url(png)}},
        ],
        "_chart_facts": facts,
    }
