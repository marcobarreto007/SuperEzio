"""Baixa tickers do dataset AYUSHKHAIRE/all-stock-market-data-daily-updates (CC0-1.0).

Estrategia: o tamanho do CSV e' proporcional ao numero de barras (schema fixo,
6 colunas). Entao ordenamos por tamanho decrescente para pegar os tickers com
historico mais longo, que e' o que o expert technical_neural precisa.

Sem token: o dataset e' publico (gated=False).

Uso:  python scripts/fetch_ayushkhaire.py --top 500
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

REPO = "AYUSHKHAIRE/all-stock-market-data-daily-updates"
API = f"https://huggingface.co/api/datasets/{REPO}/tree/main"
RAW = f"https://huggingface.co/datasets/{REPO}/resolve/main"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DEST = os.path.abspath(os.path.join(ROOT, "data", "reference", "technical_neural"))
WORK = os.path.abspath(os.path.join(ROOT, "data", "reference", ".work"))
INVENTORY = os.path.join(WORK, "ayushkhaire_inventory.json")

LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def _get(url: str, binary: bool = False, tries: int = 4, timeout: int = 120):
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "superezio-dataset-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read() if binary else r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (n + 1))
    raise RuntimeError(f"falhou apos {tries} tentativas: {url}: {last}")


def _get_with_headers(url: str, timeout: int = 120):
    req = urllib.request.Request(url, headers={"User-Agent": "superezio-dataset-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), r.headers.get("Link", "")


def build_inventory() -> list[dict]:
    """Percorre as 26 pastas seguindo a paginacao por header Link."""
    if os.path.exists(INVENTORY):
        with open(INVENTORY, encoding="utf-8") as fh:
            inv = json.load(fh)
        if inv:
            print(f"[inventario] reaproveitando cache: {len(inv)} arquivos")
            return inv

    out: list[dict] = []
    for letter in LETTERS:
        url = f"{API}/{letter}?recursive=true"
        while url:
            data, link = _get_with_headers(url)
            for entry in data:
                if entry.get("type") == "file" and entry["path"].lower().endswith(".csv"):
                    out.append({"path": entry["path"], "size": entry.get("size") or 0})
            m = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = m.group(1) if m else None
        print(f"[inventario] {letter}: {len(out)} acumulado", flush=True)

    os.makedirs(WORK, exist_ok=True)
    with open(INVENTORY, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return out


def download(path: str) -> dict:
    """Baixa um CSV e devolve metadados reais (linhas, primeira/ultima data)."""
    target = os.path.join(DEST, path.replace("/", os.sep))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    url = f"{RAW}/{urllib.parse.quote(path)}"
    if not (os.path.exists(target) and os.path.getsize(target) > 0):
        blob = _get(url, binary=True)
        tmp = target + ".part"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, target)
    size = os.path.getsize(target)
    with open(target, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {"path": path, "size": size, "rows": 0, "erro": "vazio"}
    header = rows[0]
    body = rows[1:] if header and not header[0].replace(".", "").isdigit() else rows
    if not body:
        return {"path": path, "size": size, "rows": 0, "erro": "sem dados"}
    try:
        first = int(float(body[0][-1]))
        last = int(float(body[-1][-1]))
    except (ValueError, IndexError):
        return {"path": path, "size": size, "rows": len(body), "erro": "timestamp invalido"}
    fmt = "%Y-%m-%d"
    return {
        "path": path,
        "ticker": os.path.basename(path)[:-4],
        "size": size,
        "rows": len(body),
        "inicio": dt.datetime.fromtimestamp(first, dt.UTC).strftime(fmt),
        "fim": dt.datetime.fromtimestamp(last, dt.UTC).strftime(fmt),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--top", type=int, default=500, help="quantos tickers baixar (maiores primeiro)"
    )
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    inv = build_inventory()
    print(f"[inventario] total de arquivos: {len(inv)}")
    inv.sort(key=lambda e: e["size"], reverse=True)
    chosen = inv[: args.top]
    print(f"[download] selecionados {len(chosen)} (maiores por tamanho ~= historico mais longo)")
    print(f"[download] faixa de tamanho: {chosen[-1]['size']} .. {chosen[0]['size']} bytes")

    os.makedirs(DEST, exist_ok=True)
    results, errors = [], []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download, e["path"]): e for e in chosen}
        for done, fut in enumerate(cf.as_completed(futs), 1):
            try:
                results.append(fut.result())
            except Exception as e:  # noqa: BLE001
                errors.append({"path": futs[fut]["path"], "erro": str(e)})
            if done % 50 == 0 or done == len(chosen):
                print(f"  {done}/{len(chosen)}", flush=True)

    ok = [r for r in results if not r.get("erro")]
    ok.sort(key=lambda r: r["rows"], reverse=True)
    summary = {
        "fonte": "AYUSHKHAIRE/all-stock-market-data-daily-updates",
        "baixados": len(ok),
        "erros": errors,
        "min_barras": min((r["rows"] for r in ok), default=0),
        "max_barras": max((r["rows"] for r in ok), default=0),
        "mediana_barras": sorted(r["rows"] for r in ok)[len(ok) // 2] if ok else 0,
        "com_menos_de_161_barras": sum(1 for r in ok if r["rows"] < 161),
        "ultima_data_max": max((r["fim"] for r in ok), default=None),
        "ultima_data_min": min((r["fim"] for r in ok), default=None),
        "inicio_min": min((r["inicio"] for r in ok), default=None),
        "top10_por_barras": ok[:10],
        "bytes_total": sum(r["size"] for r in ok),
    }
    with open(os.path.join(DEST, "_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "tickers": ok}, fh, indent=1)

    print("\n=== RESUMO AYUSHKHAIRE ===")
    for k in (
        "baixados",
        "min_barras",
        "mediana_barras",
        "max_barras",
        "com_menos_de_161_barras",
        "inicio_min",
        "ultima_data_min",
        "ultima_data_max",
        "bytes_total",
    ):
        print(f"  {k}: {summary[k]}")
    print(f"  erros: {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
