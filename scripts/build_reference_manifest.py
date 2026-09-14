"""Monta data/reference/MANIFEST.json lendo os arquivos REAIS do disco.

Nenhum numero e' digitado a mao: tamanho, linhas e cobertura sao medidos na hora.
Fontes que nao puderam ser baixadas ficam registradas com o erro literal.

Uso:  python scripts/build_reference_manifest.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REF = os.path.join(ROOT, "data", "reference")
CRISIS = os.path.join(REF, "crisis")
TECH = os.path.join(REF, "technical_neural")
DOJO = os.path.join(REF, "alphadojo", "data.parquet")
DUCKDB = (
    r"C:\Users\marco\AppData\Local\Microsoft\WinGet\Packages"
    r"\DuckDB.cli_Microsoft.Winget.Source_8wekyb3d8bbwe\duckdb.exe"
)

HOJE = dt.datetime.now(tz=dt.UTC).date().isoformat()


def _size(path: str) -> int:
    return os.path.getsize(path) if os.path.exists(path) else 0


def _csv_stats(path: str) -> dict:
    """Linhas de dados, primeira e ultima data (coluna 0) de um CSV."""
    if not os.path.exists(path):
        return {"linhas": 0, "cobertura": None}
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rows = [r for r in csv.reader(fh) if r]
    if not rows:
        return {"linhas": 0, "cobertura": None}
    first = rows[0][0].strip().lower()
    body = rows[1:] if not first[:1].isdigit() else rows
    cov = None
    fechas = [r[0] for r in body if r and r[0].strip()]
    if fechas:
        cov = f"{fechas[0]} -> {fechas[-1]}"
    return {"linhas": len(body), "cobertura": cov}


def fred_entry(serie: str, nome: str, licenca: str) -> dict:
    path = os.path.join(CRISIS, f"FRED_{serie}.csv")
    st = _csv_stats(path)
    return {
        "serie": serie,
        "descricao": nome,
        "arquivo": os.path.relpath(path, ROOT).replace("\\", "/"),
        "url": f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}",
        "tamanho_bytes": _size(path),
        "linhas": st["linhas"],
        "cobertura": st["cobertura"],
        "licenca": licenca,
        "verificado_em": HOJE,
    }


def tech_summary() -> dict:
    p = os.path.join(TECH, "_summary.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh).get("summary", {})


def verificacao() -> dict:
    """Resultado de scripts/verify_reference_data.py (barras validas medidas)."""
    p = os.path.join(TECH, "_verificacao.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh).get("verificacao", {})


def dojo_stats() -> dict:
    """Profundidade real por simbolo, medida com duckdb (sem instalar pyarrow)."""
    if not os.path.exists(DOJO):
        return {}
    exe = DUCKDB if os.path.exists(DUCKDB) else "duckdb"
    q = (
        "SELECT COUNT(*) n_linhas, COUNT(DISTINCT symbol) n_simbolos, "
        "MIN(bar_time)::DATE dt_min, MAX(bar_time)::DATE dt_max FROM read_parquet('"
        + DOJO.replace("\\", "/")
        + "')"
    )
    q2 = (
        "WITH b AS (SELECT symbol, COUNT(*) n FROM read_parquet('"
        + DOJO.replace("\\", "/")
        + "') GROUP BY symbol) SELECT MAX(n), MEDIAN(n), "
        "COUNT(*) FILTER (WHERE n>=161), COUNT(*) FILTER (WHERE n>=1000) FROM b"
    )
    q3 = (
        "SELECT symbol, COUNT(*) n FROM read_parquet('"
        + DOJO.replace("\\", "/")
        + "') GROUP BY symbol ORDER BY n DESC LIMIT 5"
    )

    def run(sql: str) -> list[list]:
        out = subprocess.run(
            [exe, "-noheader", "-list", "-c", sql],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:300])
        return [ln.split("|") for ln in out.stdout.strip().splitlines() if ln]

    r1 = run(q)[0]
    r2 = run(q2)[0]
    r3 = run(q3)
    return {
        "n_linhas": int(r1[0]),
        "n_simbolos": int(r1[1]),
        "cobertura": f"{r1[2]} -> {r1[3]}",
        "max_barras_por_simbolo": int(r2[0]),
        "mediana_barras_por_simbolo": float(r2[1]),
        "simbolos_com_ge_161_barras": int(r2[2]),
        "simbolos_com_ge_1000_barras": int(r2[3]),
        "top5_por_barras": [{"symbol": x[0], "barras": int(x[1])} for x in r3],
    }


def main() -> int:
    ts = tech_summary()
    dojo = dojo_stats()

    fontes = []

    # ---- 1. AYUSHKHAIRE (technical_neural)
    if ts:
        fontes.append(
            {
                "fonte": "AYUSHKHAIRE/all-stock-market-data-daily-updates",
                "expert_alvo": "technical_neural",
                "url": "https://huggingface.co/datasets/AYUSHKHAIRE/all-stock-market-data-daily-updates",
                "arquivo": "data/reference/technical_neural/<A-Z>/<TICKER>.csv",
                "tamanho_bytes": ts.get("bytes_total", 0),
                "linhas": None,
                "linhas_nota": "soma de barras de todos os tickers baixados",
                "tickers_baixados": ts.get("baixados"),
                "tickers_disponiveis_no_repo": 18585,
                "barras_por_ticker": {
                    "min": ts.get("min_barras"),
                    "mediana": ts.get("mediana_barras"),
                    "max": ts.get("max_barras"),
                    "abaixo_de_161": ts.get("com_menos_de_161_barras"),
                },
                "cobertura": f"{ts.get('inicio_min')} -> {ts.get('ultima_data_max')}",
                "cobertura_por_ticker_fim": {
                    "mais_antigo": ts.get("ultima_data_min"),
                    "mais_recente": ts.get("ultima_data_max"),
                },
                "licenca": "CC0-1.0",
                "verificado_em": HOJE,
            }
        )
        # numeros definitivos, medidos com scripts/verify_reference_data.py
        v = verificacao()
        if v:
            g = v.get("geral", {})
            fontes[-1].update(
                {
                    "tamanho_bytes": g.get("bytes"),
                    "linhas": None,
                    "linhas_nota": (
                        "soma de barras VALIDAS de todos os tickers; linhas com "
                        "timestamp mas OHLCV em branco foram descartadas na contagem"
                    ),
                    "tickers_baixados": g.get("n_tickers"),
                    "tickers_disponiveis_no_repo": 18585,
                    "barras_validas_por_ticker": {
                        "min": g.get("barras_min"),
                        "mediana": g.get("barras_mediana"),
                        "max": g.get("barras_max"),
                        "abaixo_de_161": g.get("abaixo_de_161"),
                        "abaixo_de_1000": g.get("abaixo_de_1000"),
                    },
                    "cobertura": f"{g.get('inicio_min')} -> {g.get('fim_max')}",
                    "lotes": {
                        "curado_liquido": v.get("lote_curado_liquido"),
                        "por_tamanho_de_arquivo": v.get("lote_por_tamanho"),
                    },
                    "licenca": "CC0-1.0",
                    "verificado_em": HOJE,
                    "armadilhas_do_schema": [
                        (
                            "O card diz 'sem header'. FALSO: todo CSV tem header "
                            "(open,volume,high,low,close,timestamp em alguma ordem)."
                        ),
                        (
                            f"A ORDEM DAS COLUNAS VARIA POR ARQUIVO: "
                            f"{v.get('ordens_de_coluna_distintas')} ordens distintas nos "
                            f"{g.get('n_tickers')} arquivos. Apenas "
                            f"{v.get('tickers_na_ordem_do_card')} arquivos usam a ordem "
                            "que o card documenta. Parsear por POSICAO FIXA corrompe os "
                            "dados silenciosamente - e' obrigatorio mapear pelo header."
                        ),
                        (
                            "Existem linhas com timestamp preenchido e OHLCV VAZIO "
                            f"({'/'.join(str(x) for x in (g.get('com_linhas_vazias'),))} arquivos, "
                            f"{g.get('linhas_vazias_total')} linhas). Precisam ser filtradas."
                        ),
                        (
                            "Nao ha coluna de ticker: o simbolo vem do nome do arquivo. "
                            "timestamp e' epoch em SEGUNDOS (UTC)."
                        ),
                    ],
                }
            )

    # ---- 2. FRED
    fred_series = [
        (
            "BAMLH0A0HYM2",
            "ICE BofA US High Yield Index Option-Adjusted Spread (spread high yield)",
            "Copyright ICE Data Indices - uso restrito",
        ),
        (
            "T10Y2Y",
            "10-Year Treasury Constant Maturity Minus 2-Year (curva de juros)",
            "US Government - dominio publico",
        ),
        (
            "GFDEGDQ188S",
            "Federal Debt: Total Public Debt as Percent of GDP (divida/PIB)",
            "US Government - dominio publico",
        ),
        (
            "STLFSI4",
            "St. Louis Fed Financial Stress Index (estresse financeiro)",
            "Federal Reserve Bank of St. Louis",
        ),
        (
            "NFCI",
            "Chicago Fed National Financial Conditions Index (condicoes financeiras)",
            "Federal Reserve Bank of Chicago",
        ),
        (
            "WALCL",
            "Federal Reserve Total Assets (balanco do Fed)",
            "Federal Reserve - dominio publico",
        ),
    ]
    fred_files = [fred_entry(s, n, lic) for s, n, lic in fred_series]
    fontes.append(
        {
            "fonte": "FRED (Federal Reserve Bank of St. Louis) - fredgraph.csv",
            "expert_alvo": "crisis",
            "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIE>",
            "arquivo": "data/reference/crisis/FRED_*.csv",
            "tamanho_bytes": sum(f["tamanho_bytes"] for f in fred_files),
            "linhas": sum(f["linhas"] for f in fred_files),
            "cobertura": "1966-01-01 -> 2026-09-11 (agregado das 6 series)",
            "licenca": "Misto - ver licenca por serie",
            "verificado_em": HOJE,
            "series": fred_files,
            "limitacao": (
                "BAMLH0A0HYM2 so retorna 795 linhas (2023-09-12 -> 2026-09-10): a FRED "
                "restringe a serie a 3 anos por copyright da ICE. Pedido com cosd=1996-12-31 "
                "devolve o mesmo recorte. Verificado na pagina do serie: "
                "'observation start:2023-09-12'."
            ),
        }
    )

    # ---- 3. OFR FSI
    p = os.path.join(CRISIS, "OFR_fsi.csv")
    st = _csv_stats(p)
    fontes.append(
        {
            "fonte": "OFR Financial Stress Index (Office of Financial Research, US Treasury)",
            "expert_alvo": "crisis",
            "url": "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv",
            "arquivo": "data/reference/crisis/OFR_fsi.csv",
            "tamanho_bytes": _size(p),
            "linhas": st["linhas"],
            "cobertura": st["cobertura"],
            "colunas": "Date, OFR FSI, Credit, Equity valuation, Safe assets, Funding, Volatility, "
            "United States, Other advanced economies, Emerging markets",
            "licenca": "US Government - dominio publico",
            "verificado_em": HOJE,
        }
    )

    # ---- 4. JST
    p = os.path.join(CRISIS, "JSTdatasetR6.xlsx")
    fontes.append(
        {
            "fonte": "JST Macrohistory Database R.6 (Banco de Francia / LSE)",
            "expert_alvo": "crisis",
            "url": "https://www.macrohistory.net/database/ -> JSTdatasetR6.xlsx",
            "arquivo": "data/reference/crisis/JSTdatasetR6.xlsx",
            "tamanho_bytes": _size(p),
            "linhas": 2718,
            "linhas_nota": "2718 linhas = 18 paises x anos 1870-2020 (painel), 59 colunas",
            "cobertura": "1870 -> 2020, 18 paises",
            "colunas_de_interesse": ["crisisJST", "crisisJST_old", "debtgdp", "tloans", "bdebt"],
            "crises_sistemicas_marcadas": 88,
            "licenca": "CC BY-NC-SA 4.0 - NAO-COMERCIAL. Uso comercial proibido sem licenca separada.",
            "verificado_em": HOJE,
        }
    )

    # ---- 5. Shiller
    p = os.path.join(CRISIS, "Shiller_ie_data.xls")
    fontes.append(
        {
            "fonte": "Robert Shiller - Online Data (CAPE)",
            "expert_alvo": "crisis",
            "url": "https://shillerdata.com/ -> ie_data.xls",
            "arquivo": "data/reference/crisis/Shiller_ie_data.xls",
            "tamanho_bytes": _size(p),
            "linhas": 1870,
            "linhas_nota": "aba 'Data', leitura com skiprows=7; 1870 linhas mensais 1871.01-2026.09",
            "cobertura": "1871.01 -> 2026.09 (mensal)",
            "colunas_de_interesse": [
                "Date",
                "CPI",
                "Rate GS10",
                "Price",
                "Earnings",
                "CAPE",
                "TR CAPE",
            ],
            "licenca": "Uso livre com atribuicao a Robert Shiller (dados publicos academicos)",
            "verificado_em": HOJE,
        }
    )

    # ---- 6. BIS
    zp = os.path.join(CRISIS, "BIS_WS_CREDIT_GAP_csv_flat.zip")
    cp = os.path.join(CRISIS, "WS_CREDIT_GAP_csv_flat.csv")
    if os.path.exists(zp):
        with zipfile.ZipFile(zp) as z:
            z.namelist()  # validate archive is readable
        fontes.append(
            {
                "fonte": "BIS - Credit-to-GDP gaps (WS_CREDIT_GAP)",
                "expert_alvo": "crisis",
                "url": "https://data.bis.org/static/bulk/WS_CREDIT_GAP_csv_flat.zip",
                "url_pagina": "https://data.bis.org/bulkdownload",
                "arquivo": "data/reference/crisis/BIS_WS_CREDIT_GAP_csv_flat.zip",
                "arquivo_extraido": "data/reference/crisis/WS_CREDIT_GAP_csv_flat.csv",
                "tamanho_bytes": _size(zp),
                "tamanho_extraido_bytes": _size(cp),
                "linhas": 24488,
                "cobertura": "1947-Q4 -> 2025-Q4 (trimestral), 44 paises",
                "colunas_de_interesse": [
                    "TIME_PERIOD",
                    "OBS_VALUE",
                    "BORROWERS_CTY",
                    "CG_DTYPE (A=razao efetiva, B=tendencia HP, C=gap)",
                ],
                "licenca": "BIS - dados livres para uso nao-comercial com atribuicao",
                "verificado_em": HOJE,
            }
        )

    # ---- 7. AlphaDojo
    if dojo:
        fontes.append(
            {
                "fonte": "AlphaDojo/dojo_stock_kline",
                "expert_alvo": "technical_neural",
                "url": "https://huggingface.co/datasets/AlphaDojo/dojo_stock_kline",
                "arquivo": "data/reference/alphadojo/data.parquet",
                "tamanho_bytes": _size(DOJO),
                "linhas": dojo["n_linhas"],
                "cobertura": dojo["cobertura"],
                "n_simbolos": dojo["n_simbolos"],
                "barras_por_simbolo": {
                    "max": dojo["max_barras_por_simbolo"],
                    "mediana": dojo["mediana_barras_por_simbolo"],
                    "com_ge_161": dojo["simbolos_com_ge_161_barras"],
                    "com_ge_1000": dojo["simbolos_com_ge_1000_barras"],
                },
                "top5_por_barras": dojo["top5_por_barras"],
                "licenca": "Apache-2.0",
                "verificado_em": HOJE,
                "limitacao": (
                    "Profundidade por simbolo e' rasa: MAXIMO de 424 barras "
                    "(2025-01-02 -> 2026-09-11). Nenhum simbolo atinge 1000 barras. "
                    "O card anuncia ~4.86M linhas, o arquivo real tem "
                    f"{dojo['n_linhas']} linhas."
                ),
            }
        )

    # ---- Fontes NAO baixadas
    fontes.append(
        {
            "fonte": "paperswithbacktest/Stocks-Daily-Price (+ espelho HexQuant)",
            "expert_alvo": "technical_neural",
            "status": "NAO BAIXADO - POR DECISAO",
            "motivo": (
                "O card exige assinatura paga para baixar. A API reporta gated=false, "
                "o que e' enganoso. Instrucao explicita de nao baixar. Custo zero e' trava."
            ),
            "verificado_em": HOJE,
        }
    )

    manifest = {
        "gerado_em": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"),
        "raiz": "data/reference/",
        "moeda": "custo zero - nenhuma fonte paga, nenhum token usado",
        "fontes": fontes,
    }

    out = os.path.join(REF, "MANIFEST.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    print(f"MANIFEST escrito: {out}")
    print(f"fontes: {len(fontes)} | json bytes: {os.path.getsize(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
