"""Varredura de verificacao de TODOS os CSVs do technical_neural.

Mede o que o expert realmente consome:
  - barras VALIDAS (linha com timestamp E campos de preco preenchidos)
  - linhas vazias (timestamp presente, OHLCV em branco) - lixo que precisa ser filtrado
  - ordens de coluna distintas (a ordem VARIA por arquivo)
  - cobertura real de datas

Saida: data/reference/technical_neural/_verificacao.json

Uso:  python scripts/verify_reference_data.py
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TECH = os.path.join(ROOT, "data", "reference", "technical_neural")
OUT = os.path.join(TECH, "_verificacao.json")

PRICE_COLS = ("open", "high", "low", "close")


def scan(path: str, batch: str) -> dict:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = [r for r in csv.reader(fh) if r]
    if not rows:
        return {"erro": "vazio"}
    header = [h.strip().lower() for h in rows[0]]
    if "timestamp" not in header:
        return {"erro": "sem timestamp"}
    i_ts = header.index("timestamp")
    icols = [header.index(c) for c in PRICE_COLS if c in header]
    body = rows[1:]
    validos, vazios = [], 0
    for r in body:
        if len(r) <= i_ts or not r[i_ts].strip():
            vazios += 1
            continue
        if not all(len(r) > i and r[i].strip() for i in icols):
            vazios += 1
            continue
        try:
            validos.append(int(float(r[i_ts])))
        except ValueError:
            vazios += 1
    if not validos:
        return {"erro": "sem barras validas"}
    fmt = "%Y-%m-%d"
    return {
        "ticker": os.path.basename(path)[:-4],
        "lote": batch,
        "ordem_colunas": ",".join(header),
        "linhas_totais": len(body),
        "barras_validas": len(validos),
        "linhas_vazias": vazios,
        "inicio": dt.datetime.fromtimestamp(min(validos), dt.UTC).strftime(fmt),
        "fim": dt.datetime.fromtimestamp(max(validos), dt.UTC).strftime(fmt),
        "bytes": os.path.getsize(path),
    }


def main() -> int:
    files = sorted(glob.glob(os.path.join(TECH, "*", "*.csv")))
    print(f"arquivos encontrados: {len(files)}")
    res = []
    for i, f in enumerate(files, 1):
        batch = "curado_liquido" if _is_liquid(f) else "tamanho"
        try:
            r = scan(f, batch)
        except Exception as e:  # noqa: BLE001
            r = {"erro": str(e), "ticker": os.path.basename(f)}
        res.append(r)
        if i % 200 == 0:
            print(f"  {i}/{len(files)}", flush=True)

    ok = [r for r in res if "barras_validas" in r]
    bad = [r for r in res if "barras_validas" not in r]
    ordens = {r["ordem_colunas"] for r in ok}
    barras = [r["barras_validas"] for r in ok]

    liq = [r for r in ok if r["lote"] == "curado_liquido"]
    tam = [r for r in ok if r["lote"] == "tamanho"]

    def bloco(rs: list[dict]) -> dict:
        if not rs:
            return {}
        b = [r["barras_validas"] for r in rs]
        return {
            "n_tickers": len(rs),
            "barras_min": min(b),
            "barras_mediana": int(statistics.median(b)),
            "barras_max": max(b),
            "abaixo_de_161": sum(1 for x in b if x < 161),
            "abaixo_de_1000": sum(1 for x in b if x < 1000),
            "com_linhas_vazias": sum(1 for r in rs if r["linhas_vazias"] > 0),
            "linhas_vazias_total": sum(r["linhas_vazias"] for r in rs),
            "inicio_min": min(r["inicio"] for r in rs),
            "fim_max": max(r["fim"] for r in rs),
            "bytes": sum(r["bytes"] for r in rs),
        }

    verif = {
        "verificado_em": dt.date.today().isoformat(),
        "arquivos": len(files),
        "arquivos_ok": len(ok),
        "arquivos_com_erro": [{"ticker": r.get("ticker"), "erro": r.get("erro")} for r in bad],
        "ordens_de_coluna_distintas": len(ordens),
        "ordem_do_card_diz_ser_fixa": "open,volume,high,low,close,timestamp",
        "tickers_na_ordem_do_card": sum(
            1 for r in ok if r["ordem_colunas"] == "open,volume,high,low,close,timestamp"
        ),
        "geral": bloco(ok),
        "lote_curado_liquido": bloco(liq),
        "lote_por_tamanho": bloco(tam),
        "top10_barras_validas": sorted(ok, key=lambda r: r["barras_validas"], reverse=True)[:10],
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"verificacao": verif, "por_ticker": ok}, fh, indent=1, ensure_ascii=False)

    print("\n=== VERIFICACAO technical_neural ===")
    for k, v in verif.items():
        if k.startswith(("top10", "arquivos_com")):
            continue
        print(f"  {k}: {v}")
    return 0


_LIQ_CACHE: dict[str, set[str]] = {}


def _is_liquid(path: str) -> bool:
    if "liq" not in _LIQ_CACHE:
        p = os.path.join(TECH, "_summary_liquid.json")
        try:
            with open(p, encoding="utf-8") as fh:
                _LIQ_CACHE["liq"] = {t["arquivo"] for t in json.load(fh)["tickers"]}
        except Exception:  # noqa: BLE001
            _LIQ_CACHE["liq"] = set()
    rel = os.path.relpath(path, TECH).replace("\\", "/")
    return rel in _LIQ_CACHE["liq"]


if __name__ == "__main__":
    sys.exit(main())
