"""Baixa um conjunto CURADO de tickers liquidos do AYUSHKHAIRE (CC0-1.0).

Por que existe: selecionar pelos MAIORES arquivos pegou cascas sub-penny
(preco 9.999999747378752e-05), cujo tamanho e' inflado pela representacao
float de alta precisao, e nao por dados uteis. 460/500 tinham volume ZERO na
ultima barra. Tickers liquidos tem ~380KB e dados reais.

Armadilha do schema: a ORDEM DAS COLUNAS VARIA por arquivo (87 ordens
distintas em 500 arquivos). Todo parsing aqui e' feito pelo HEADER, nunca por
posicao fixa.

Uso:  python scripts/fetch_ayushkhaire_liquid.py
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

REPO = "AYUSHKHAIRE/all-stock-market-data-daily-updates"
RAW = f"https://huggingface.co/datasets/{REPO}/resolve/main"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEST = os.path.abspath(os.path.join(ROOT, "data", "reference", "technical_neural"))

# Tickers liquidos, listados desde antes de 2010, de setores variados.
# Inclui acoes e alguns REITs/ADR/financeiras. Sem ETFs (o repo nao os tem).
CURATED = """
AAPL MSFT AMZN GOOGL GOOG META NVDA ORCL CRM ADBE INTC AMD TXN QCOM MU AMAT
CSCO IBM HPQ DELL NTAP WDC STX GLW APH TEL MSI ROK APTV BWA LEA MGA
JPM BAC WFC C GS MS USB PNC TFC BK STT NTRS SCHW AXP COF AIG MET PRU AFL
ALL TRV CB PGR BRK-B HIG LNC UNM CINF WRB RE
JNJ PFE MRK ABBV LLY BMY AMGN GILD BIIB VRTX REGN MRNA TMO DHR ABT SYK BSX
MDT BDX ZBH BAX ISRG EW A HOLX ALGN RMD COO STE WAT MTD
XOM CVX COP EOG OXY PXD SLB HAL BKR MRO APA DVN FANG HES VLO MPC PSX OKE
WMB KMI ET EPD TRGP LNG
CAT DE HON GE MMM BA LMT RTX NOC GD LHX TDG PCP ITW EMR ETN PH ROK CMI
PCAR AGCO CNH IR XYL GWW FAST WSO SNA SWK TTC
WMT COST TGT HD LOW TJX ROST DG DLTR KR SFM BIG M KSS JWN GPS BKE DKS
NKE LULU RL PVH VFC HBI UAA UA SKX CROX DECK
SBUX MCD YUM CMG DRI QSR WEN JACK TXRH DENN EAT
KO PEP MNST KDP STZ BF-B TAP SAM CELH
PG CL KMB CHD COLG ENR EL COTY EPC NWL MAT HAS
V MA PYPL FIS FISV GPN WU FISV JKHY BR
DIS CMCSA CHTR NFLX WBD PARA FOXA NWSA SIRI LBRDA TGNA
T VZ TMUS LUMN
UPS FDX UNP CSX NSC CP RTX ODFL XPO CHRW EXPD JBHT
LIN APD SHW ECL PPG RPM NEM FCX NUE STLD CLF X AA VMC MLM
DOW DD DUPONT LYBB EMN CE ALB IFF
SO DUK D NEE AEP EXC XEL ED PEG EIX WEC ES AEE DTE PPL CMS CNP FE AES
NRG VST CEG
AMT PLD EQIX CCI SPG O VTR WELL ARE BXP AVB EQR ESS MAA UDR CPT PSA EXR
DOC KIM REG FRT HST
BAX K HCSC HSIC PDCO
GILD TECH BIO
MMM SWK SNA
"""


def _get(url: str, tries: int = 4, timeout: int = 120) -> bytes:
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "superezio-dataset-fetch/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (n + 1))
    raise RuntimeError(f"falhou: {url}: {last}")


def fetch(ticker: str) -> dict:
    letter = ticker[0].upper()
    rel = f"{letter}/{ticker}.csv"
    target = os.path.join(DEST, letter, f"{ticker}.csv")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    url = f"{RAW}/{urllib.parse.quote(rel)}"
    if not (os.path.exists(target) and os.path.getsize(target) > 0):
        blob = _get(url)
        tmp = target + ".part"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, target)
    size = os.path.getsize(target)
    with open(target, newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return {"ticker": ticker, "erro": "vazio", "size": size}
    header = [h.strip().lower() for h in rows[0]]
    if "timestamp" not in header:
        os.remove(target)
        return {"ticker": ticker, "erro": f"sem header de timestamp: {rows[0][:6]}", "size": size}
    i_ts = header.index("timestamp")
    i_vol = header.index("volume") if "volume" in header else None
    i_cls = header.index("close") if "close" in header else None
    body = rows[1:]
    first = int(float(body[0][i_ts]))
    last = int(float(body[-1][i_ts]))
    fmt = "%Y-%m-%d"
    out = {
        "ticker": ticker,
        "arquivo": f"{letter}/{ticker}.csv",
        "size": size,
        "rows": len(body),
        "ordem_colunas": ",".join(header),
        "inicio": dt.datetime.fromtimestamp(first, dt.UTC).strftime(fmt),
        "fim": dt.datetime.fromtimestamp(last, dt.UTC).strftime(fmt),
    }
    if i_cls is not None and i_vol is not None:
        out["close_final"] = float(body[-1][i_cls])
        out["volume_final"] = float(body[-1][i_vol])
    return out


def main() -> int:
    tickers = []
    seen = set()
    for t in CURATED.split():
        t = t.strip().upper()
        if t and t not in seen:
            seen.add(t)
            tickers.append(t)
    print(f"[curado] {len(tickers)} tickers liquidos")

    results, errors = [], []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch, t): t for t in tickers}
        for fut in cf.as_completed(futs):
            try:
                r = fut.result()
                (errors if r.get("erro") else results).append(r)
            except Exception as e:  # noqa: BLE001
                errors.append({"ticker": futs[fut], "erro": str(e)})

    results.sort(key=lambda r: r["rows"], reverse=True)
    zero_vol = sum(1 for r in results if r.get("volume_final") == 0)
    sub_penny = sum(1 for r in results if (r.get("close_final") or 1) < 0.01)
    summary = {
        "baixados": len(results),
        "erros": len(errors),
        "min_barras": min((r["rows"] for r in results), default=0),
        "mediana_barras": sorted(r["rows"] for r in results)[len(results) // 2] if results else 0,
        "max_barras": max((r["rows"] for r in results), default=0),
        "com_menos_de_161_barras": sum(1 for r in results if r["rows"] < 161),
        "volume_zero_no_final": zero_vol,
        "sub_penny_no_final": sub_penny,
        "inicio_min": min((r["inicio"] for r in results), default=None),
        "ultima_data_max": max((r["fim"] for r in results), default=None),
        "bytes_total": sum(r["size"] for r in results),
        "detalhe_erros": errors[:20],
        "top10_por_barras": results[:10],
    }
    with open(os.path.join(DEST, "_summary_liquid.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "tickers": results}, fh, indent=1)

    print("\n=== RESUMO CURADO (LIQUIDOS) ===")
    for k in (
        "baixados",
        "erros",
        "min_barras",
        "mediana_barras",
        "max_barras",
        "com_menos_de_161_barras",
        "volume_zero_no_final",
        "sub_penny_no_final",
        "inicio_min",
        "ultima_data_max",
        "bytes_total",
    ):
        print(f"  {k}: {summary[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
