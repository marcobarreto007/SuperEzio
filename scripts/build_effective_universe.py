#!/usr/bin/env python
"""build_effective_universe.py -- universo NEGOCIAVEL EFETIVO do SuperEzio.

Responde tres perguntas que nunca foram feitas sobre os 108 ETFs commission-free
de `config/td_direct_commission_free_etfs.json`:

  1. Quantas EXPOSICOES DISTINTAS esses 108 representam?
     (o protocolo do projeto tem a regra "ETF OVERLAP: correlacao > 0.95 = mesmo ativo")
  2. Quais passam na regra de FRICCAO do protocolo?
     (comissao + spread <= 0.5% da ordem)
  3. Quais tem HISTORICO suficiente para os experts trabalharem?
     (technical_neural exige >= 161 barras; alvo 1000+)

Saida: config/td_universe_effective.json

ESCOPO: este script escreve APENAS em `config/` e `data/reference/`.
Nao importa nada de `src/` e nao toca em `tests/`.
CUSTO: zero. yfinance e gratuito e nao pede cartao.

Uso:
    python scripts/build_effective_universe.py             # usa cache local
    python scripts/build_effective_universe.py --refresh    # rebaixa do yfinance
    python scripts/build_effective_universe.py --cutoffs 0.95,0.90,0.85
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC_ETF_LIST = os.path.join(ROOT, "config", "td_direct_commission_free_etfs.json")
OUT_JSON = os.path.join(ROOT, "config", "td_universe_effective.json")
CACHE_DIR = os.path.join(ROOT, "data", "reference", "effective_universe")
OHLCV_DIR = os.path.join(CACHE_DIR, "ohlcv")

# ---------------------------------------------------------------- parametros

CORR_WINDOW_YEARS = 3  # janela da matriz de correlacao (spec: "~2-3 anos")
CORR_CUTOFF_DEFAULT = 0.95  # regra do protocolo: ETF OVERLAP
CORR_CUTOFFS_SENSITIVITY = [0.95, 0.90, 0.85, 0.99]
MIN_OVERLAP_BARS = 250  # abaixo disso a correlacao par-a-par nao vale
MIN_BARS_TARGET = 1000  # alvo de historico do projeto
MIN_BARS_TECHNICAL_NEURAL = 161  # minimo duro do expert technical_neural

FRICTION_CAP_PCT = 0.5  # protocolo: comissao + spread <= 0.5% da ORDEM
COMMISSION_PCT = 0.0  # commission-free (TD Direct Investing, lista oficial)
ORDER_CAD = 300.0  # ordem tipica: banca 1000 CAD, risco 1.0-1.5%

STALE_ZERO_RETURN_PCT = 20.0  # >20% de dias sem variacao = serie morta p/ barra diaria

TTL_DAYS = 7
FX_TICKER = "CAD=X"  # USDCAD

# ------------------------------------------------------------------- taxonomia
# `exposure_label` e DERIVADO do nome factual do fundo (campo `fund_name`, obtido
# do Yahoo Finance) por estas regras regex, em ORDEM de especificidade -- primeira
# que casa vence. A ordem e: geografia+classe especifica antes de estilo generico.
# Nao ha rotulo inventado a mao: nenhuma regra casando => 'unclassified', e o
# simbolo e reportado nominalmente.
EXPOSURE_RULES: list[tuple[str, str]] = [
    # ---- cripto
    (r"bitcoin", "crypto_bitcoin"),
    (r"ethereum", "crypto_ether"),
    # ---- commodities
    (r"gold miners", "gold_miners"),
    (r"gold shares|gold trust|\bgold\b", "gold_bullion"),
    (r"commodit", "commodities_broad"),
    # ---- renda fixa: alvo/vencimento e high yield vem antes do generico
    (r"high yield bond", "us_high_yield_bond"),
    (r"target 20\d\d", "bond_target_maturity"),
    (r"20\+ year treasury|long[- ]term treasury|long term treasury", "us_treasury_long"),
    (r"u\.s\. long term treasury|long term treasury bond", "us_treasury_long"),
    (r"short[- ]term corporate bond", "us_corp_bond_short"),
    (r"preferred share", "ca_preferred_share"),
    (r"cash management", "cash_equivalent"),
    (r"canadian aggregate bond", "ca_bond_aggregate"),
    (r"canadian long term federal bond", "ca_treasury_long"),
    (
        r"select short term corporate bond|canadian short[- ]term corporate bond",
        "ca_corp_bond_short",
    ),
    (r"canadian corporate bond|short term bond fund|ultra short term bond", "ca_bond_short"),
    (r"global fixed income|global income", "global_bond"),
    # ---- renda fixa EUA (large/agregado)
    (r"long government|treasury", "us_treasury_long"),
    # ---- acoes: categoria global/especifica antes de pais generico
    (r"global real estate", "global_real_estate"),
    (r"global infrastructure|infrastructure", "global_infrastructure"),
    (r"global technology", "global_tech"),
    (r"global minimum volatility", "global_min_volatility"),
    (r"global multifactor", "global_multifactor"),
    (r"global enhanced dividend|global dividend", "global_equity_dividend"),
    (r"global equity growth", "global_equity_growth"),
    (r"all cap ex canada", "global_equity_ex_ca"),
    (r"semiconductor", "us_semiconductor"),
    (r"information technology", "us_tech_sector"),
    (r"health care|healthcare", "us_healthcare"),
    (r"emerging market", "em_equity"),
    (r"international low volatility", "intl_low_volatility"),
    (r"international high dividend", "intl_dividend"),
    (
        (
            r"international equity|developed ex north america|"
            r"developed all cap ex north amer|developed europe|europe all cap"
        ),
        "intl_developed_equity",
    ),
    (r"innovation", "us_innovation_arkk"),
    (r"nasdaq", "us_nasdaq100"),
    (r"dow jones", "us_dow30"),
    (r"s&p 500", "us_sp500"),
    # ---- acoes Canada (antes dos estilos genericos de dividendo)
    (r"canadian banks|canadian bank", "ca_banks"),
    (r"ftse canada|canadian equity|canadian dividend", "ca_equity"),
    (r"canadian low volatility", "ca_low_volatility"),
    # ---- acoes EUA por estilo
    (r"real estate", "real_estate"),
    (r"russell 2000|small[- ]mid[- ]cap|small[- ]cap|small cap", "us_small_cap"),
    (r"u\.s\. low volatility|minimum volatility", "us_min_volatility"),
    (r"multifactor", "us_multifactor"),
    (r"morningstar growth|\bgrowth etf\b", "us_large_cap_growth"),
    (r"total market|total stock market", "us_total_market"),
    (r"north american dividend", "north_america_dividend"),
    (r"enhanced dividend", "us_enhanced_dividend"),
    (r"dividend appreciation", "us_dividend_appreciation"),
    (r"high dividend yield", "us_dividend_yield"),
    (r"dividend equity", "us_dividend_equity"),
    (r"u\.s\. equity", "us_large_cap_broad"),
    # ---- portfolios all-in-one (asset allocation)
    (r"all[- ]equity etf portfolio", "portfolio_all_equity"),
    (r"growth etf portfolio", "portfolio_growth"),
    (r"balanced etf portfolio", "portfolio_balanced"),
    (r"conservative etf portfolio", "portfolio_conservative"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: str):
    """Le um JSON com context manager (sem descritor pendurado)."""
    import json as _json

    with open(path, encoding="utf-8") as fh:
        return _json.load(fh)


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _r(v, nd):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def median(xs) -> float | None:
    xs = sorted(x for x in xs if x is not None and not math.isnan(x))
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def pct(xs, q) -> float | None:
    xs = sorted(x for x in xs if x is not None and not math.isnan(x))
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(q * len(xs)))]


# ------------------------------------------------------------------ ticker map


def yahoo_ticker(symbol: str, market: str) -> str:
    """TSX usa sufixo .TO; classes `.U` (USD) e `.B` viram `-U.TO` / `-B.TO`."""
    if market == "CAN":
        return symbol.replace(".", "-") + ".TO"
    return symbol


def listing_currency(symbol: str, market: str) -> str:
    """Moeda em que a serie de precos do Yahoo esta cotada.

    Classes `.U` da TSX sao series em USD do mesmo fundo -> precisam de conversao.
    """
    if market == "CAN":
        return "USD" if symbol.endswith(".U") else "CAD"
    return "USD"


def load_symbols() -> list[dict[str, Any]]:
    cfg = load_json(SRC_ETF_LIST)
    sym = cfg["symbols"]
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for market in ("CAN", "US", "USA"):
        for s in sym.get(market, []):
            if s not in seen:
                seen[s] = {"symbol": s, "markets": [], "listing": market}
                order.append(s)
            if market not in seen[s]["markets"]:
                seen[s]["markets"].append(market)
    out = []
    for s in order:
        rec = seen[s]
        rec["market"] = rec["listing"]
        rec["yahoo"] = yahoo_ticker(s, rec["listing"])
        rec["currency"] = listing_currency(s, rec["listing"])
        out.append(rec)
    return out


# ------------------------------------------------------------------- download


def _normalize_index(df):
    """Indice sem fuso, normalizado para a DATA do pregao (cache e download batem)."""
    idx = df.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx.normalize()
    df.index.name = "Date"
    return df


def fetch_one(yahoo: str, refresh: bool) -> dict[str, Any]:
    """Devolve a serie OHLCV. O erro e guardado LITERALMENTE -- nada e inventado."""
    import pandas as pd

    os.makedirs(OHLCV_DIR, exist_ok=True)
    path = os.path.join(OHLCV_DIR, yahoo.replace("/", "_").replace("=", "_") + ".csv")
    if os.path.exists(path) and not refresh:
        try:
            df = pd.read_csv(path)
            df.columns = [str(c).strip() for c in df.columns]
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_localize(None)
                df = df.set_index("Date")
            else:
                df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
                df.index.name = "Date"
            df = _normalize_index(df)
            if len(df):
                return {"df": df, "error": None, "source": "cache", "cache_path": path}
        except Exception as e:  # noqa: BLE001
            log(f"    cache ilegivel ({type(e).__name__}: {e}), rebaixando")

    import yfinance as yf

    try:
        df = yf.Ticker(yahoo).history(period="max", interval="1d", auto_adjust=True)
        if df is None or len(df) == 0:
            return {
                "df": None,
                "error": "empty history (0 bars) for period=max",
                "source": "yfinance",
                "cache_path": None,
            }
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        df = _normalize_index(df)
        out = df.copy()
        out.to_csv(path, date_format="%Y-%m-%d")
        return {"df": df, "error": None, "source": "yfinance", "cache_path": path}
    except Exception as e:  # noqa: BLE001
        return {
            "df": None,
            "error": f"{type(e).__name__}: {e}",
            "source": "yfinance",
            "cache_path": None,
        }


def fetch_names(symbols, refresh: bool) -> dict[str, dict[str, Any]]:
    """Nome factual do fundo (Yahoo). Cacheado; falha nao e fatal."""
    import yfinance as yf

    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, "fund_names.json")
    cache: dict[str, dict[str, Any]] = {}
    if os.path.exists(cache_path) and not refresh:
        cache = load_json(cache_path)

    changed = False
    for s in symbols:
        key = s["symbol"]
        if cache.get(key, {}).get("fund_name"):
            continue
        try:
            info = yf.Ticker(s["yahoo"]).info or {}
            cache[key] = {
                "fund_name": info.get("longName") or info.get("shortName"),
                "yahoo_category": info.get("category"),
                "quote_type": info.get("quoteType"),
                "error": None,
            }
        except Exception as e:  # noqa: BLE001
            cache[key] = {"fund_name": None, "error": f"{type(e).__name__}: {e}"}
        changed = True
        time.sleep(0.2)
    if changed:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=1, ensure_ascii=False)
    return cache


# --------------------------------------------------------------------- calculo


def label_from_name(name: str | None) -> str:
    if not name:
        return "unclassified"
    low = name.lower()
    for pattern, label in EXPOSURE_RULES:
        if re.search(pattern, low):
            return label
    return "unclassified"


def fund_identity(name: str | None) -> str | None:
    """Identidade economica do fundo: nome factual sem o sufixo de MOEDA.

    'TD Global Healthcare Leaders Index ETF USD' e 'TD Global Healthcare Leaders
    Index ETF' sao o MESMO fundo, duas classes de unidades. Isso e fato do
    prospectus, nao inferencia estatistica -- por isso entra como eixo proprio,
    separado da correlacao.
    """
    if not name:
        return None
    return re.sub(r"\s+(USD|US\$|CAD|C\$)\s*$", "", name.strip(), flags=re.IGNORECASE)


def zero_return_pct(df, window: int = 252) -> float | None:
    """% de pregoes recentes com retorno exatamente zero -> serie morta/iliquida."""
    if df is None or len(df) < 10:
        return None
    c = df["Close"].astype(float).iloc[-window:]
    c = c[c > 0]
    if len(c) < 10:
        return None
    r = c.pct_change().dropna()
    if not len(r):
        return None
    return float((r.abs() < 1e-9).mean() * 100.0)


def corwin_schultz_spread(df) -> list[float]:
    """Estimador de spread bid-ask de Corwin & Schultz (2012, J. Finance).

    Usa APENAS high/low de dias consecutivos. E o melhor estimador de spread
    disponivel com o dado que temos (nao ha NBBO gratuito sem cartao).
    Retorna a serie de spreads diarios como FRACAO do preco (0.001 = 0,10%).

    E ESTIMATIVA, nao observacao de tela.
    """
    h = [float(x) for x in df["High"]]
    lo_ = [float(x) for x in df["Low"]]
    n = len(h)
    out: list[float] = []
    k = 3.0 - 2.0 * math.sqrt(2.0)
    for t in range(1, n):
        h0, l0, h1, l1 = h[t - 1], lo_[t - 1], h[t], lo_[t]
        if not (h0 > 0 and l0 > 0 and h1 > 0 and l1 > 0 and h1 >= l1 and h0 >= l0):
            continue
        beta = math.log(h1 / l1) ** 2 + math.log(h0 / l0) ** 2
        hi, low = max(h1, h0), min(l1, l0)
        if low <= 0 or beta <= 0 or 2.0 * beta <= 0:
            continue
        gamma = math.log(hi / low) ** 2
        if gamma <= 0:
            continue
        try:
            alpha = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        except ValueError:
            continue
        e = math.exp(min(alpha, 50.0))
        out.append(max(2.0 * (e - 1.0) / (1.0 + e), 0.0))  # paper trunca < 0 em 0
    return out


def range_proxy(df) -> float | None:
    """Proxy BRUTO: mediana de (high-low)/close. Teto conservador, NAO o spread."""
    vals = []
    for hi, lo, c in zip(df["High"], df["Low"], df["Close"]):
        try:
            hi, lo, c = float(hi), float(lo), float(c)
        except (TypeError, ValueError):
            continue
        if c and c > 0 and hi >= lo >= 0:
            vals.append((hi - lo) / c)
    return median(vals)


def build_returns(dfs, currency, fx, window_years, common_currency):
    """Retornos LOG diarios, opcionalmente normalizados a uma moeda comum.

    Normalizar importa: VFV (S&P500 em CAD) e VOO (S&P500 em USD) sao a MESMA
    exposicao; sem normalizar, a correlacao mede o USDCAD junto e as duas caem
    abaixo do corte. Correlacao de exposicao exige moeda comum.
    """
    frames = {}
    for sym, df in dfs.items():
        if df is None or len(df) < 2:
            continue
        s = df["Close"].astype(float)
        s = s[s > 0].iloc[-(252 * window_years) :]
        if len(s) < 2:
            continue
        r = s.map(math.log).diff()
        if common_currency and currency.get(sym) == "USD" and fx is not None and len(fx):
            f = fx.reindex(s.index).ffill().bfill()
            f = f[f > 0]
            if len(f) >= 2:
                r = r.add(f.map(math.log).diff(), fill_value=0.0)
        frames[sym] = r
    return frames


def corr_matrices(frames, min_overlap):
    import pandas as pd

    if not frames:
        return None, None, {}
    px = pd.DataFrame(frames).sort_index()
    rets = px.replace([math.inf, -math.inf], float("nan")).dropna(how="all")
    corr = rets.corr(min_periods=min_overlap)
    mask = rets.notna().astype(int)
    overlap = mask.T.dot(mask)
    return corr, overlap, {k: int(v) for k, v in mask.sum().items()}


def _valid_pairs(corr, overlap, min_overlap):
    from itertools import combinations

    syms = list(corr.columns)
    out = []
    for a, b in combinations(syms, 2):
        c = corr.at[a, b]
        if c is None or (isinstance(c, float) and math.isnan(c)):
            continue
        if overlap is not None and int(overlap.at[a, b]) < min_overlap:
            continue
        out.append((float(c), a, b))
    out.sort(key=lambda t: (-t[0], t[1], t[2]))
    return out


def single_linkage_clusters(corr, overlap, cutoff, min_overlap) -> list[list[str]]:
    """Clusterizacao por CONEXAO (single-linkage) -- leitura LITERAL da regra.

    "correlacao > cutoff => mesmo ativo", aplicado par a par. E o que a regra do
    projeto diz, mas ENCADEIA: se A~B e B~C mas A!~C, os tres viram um grupo so.
    Basta uma ponte para fundir coisas que NAO sao a mesma exposicao.
    """
    syms = list(corr.columns)
    parent = {s: s for s in syms}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for c, a, b in _valid_pairs(corr, overlap, min_overlap):
        if c < cutoff:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    groups: dict[str, list[str]] = {}
    for s in syms:
        groups.setdefault(find(s), []).append(s)
    return list(groups.values())


def complete_linkage_clusters(corr, overlap, cutoff, min_overlap) -> list[list[str]]:
    """Clusterizacao por COESAO TOTAL -- sem encadeamento.

    So funde dois grupos se TODOS os pares cruzados estiverem >= cutoff. E a
    leitura que de fato responde "quantas exposicoes distintas": um grupo onde
    TODO membro e o mesmo ativo. Guloso, deterministico (pares em ordem
    decrescente de correlacao, desempate por nome).
    """
    syms = list(corr.columns)
    clusters: dict[str, list[str]] = {s: [s] for s in syms}
    owner = {s: s for s in syms}

    for c, a, b in _valid_pairs(corr, overlap, min_overlap):
        if c < cutoff:
            break
        ca, cb = owner[a], owner[b]
        if ca == cb:
            continue
        ma, mb = clusters[ca], clusters[cb]
        ok = True
        for x in ma:
            for y in mb:
                v = corr.at[x, y]
                if v is None or (isinstance(v, float) and math.isnan(v)) or v < cutoff:
                    ok = False
                    break
                if overlap is not None and int(overlap.at[x, y]) < min_overlap:
                    ok = False
                    break
            if not ok:
                break
        if ok:
            merged = sorted(ma + mb)
            clusters[ca] = merged
            del clusters[cb]
            for s in merged:
                owner[s] = ca
    return [sorted(v) for v in clusters.values()]


def add_identity_edges(groups, ident: dict[str, str | None]) -> list[list[str]]:
    """Une clusters ligados por IDENTIDADE DE FUNDO (mesmo fundo, outra moeda)."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for g in groups:
        for m in g:
            find(m)
        for m in g[1:]:
            union(g[0], m)
    by_ident: dict[str, list[str]] = {}
    for sym, fid in ident.items():
        if fid:
            by_ident.setdefault(fid, []).append(sym)
    for fid, members in by_ident.items():
        if len(members) > 1:
            for m in members[1:]:
                union(members[0], m)
    out: dict[str, list[str]] = {}
    allsyms = {s for g in groups for s in g} | {s for s, f in ident.items() if f}
    for s in allsyms:
        out.setdefault(find(s), []).append(s)
    return list(out.values())


def _pair_frame(ra, rb) -> float | None:
    """Correlacao entre duas series de retorno ja alinhadas (por nome de data)."""
    import pandas as pd

    j = pd.concat([ra, rb], axis=1, keys=["a", "b"], sort=True).dropna()
    if len(j) < MIN_OVERLAP_BARS:
        return None
    a = j["a"].to_numpy(dtype=float)
    b = j["b"].to_numpy(dtype=float)
    sa, sb = a.std(), b.std()
    if sa == 0 or sb == 0:
        return None
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def min_intra_corr(members, corr) -> float | None:
    vals = []
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            c = corr.at[a, b]
            if c is not None and not (isinstance(c, float) and math.isnan(c)):
                vals.append(float(c))
    return min(vals) if vals else None


def name_clusters(groups, labels, bars):
    """cluster_id derivado do rotulo mais frequente entre os MEMBROS (dado, nao escolha)."""
    named = []
    for members in groups:
        ms = sorted(members)
        counts: dict[str, int] = {}
        for m in ms:
            lab = labels.get(m, "unclassified")
            counts[lab] = counts.get(lab, 0) + 1
        best = min(
            counts.items(),
            key=lambda kv: (
                -kv[1],
                -max((bars.get(m, 0) for m in ms if labels.get(m) == kv[0]), default=0),
                kv[0],
            ),
        )[0]
        rep = max(ms, key=lambda m: (bars.get(m, 0), m))
        if counts[best] * 2 < len(ms):
            best = f"{best}_mixed"
        named.append({"members": ms, "base_label": best, "representative": rep})

    seen: dict[str, int] = {}
    out = []
    for c in sorted(named, key=lambda t: (-len(t["members"]), t["members"][0])):
        seen[c["base_label"]] = seen.get(c["base_label"], 0) + 1
        cid = (
            c["base_label"]
            if seen[c["base_label"]] == 1
            else f"{c['base_label']}_{seen[c['base_label']]}"
        )
        c["cluster_id"] = cid
        out.append(c)
    return out


# ------------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description="Constroi o universo negociavel efetivo.")
    ap.add_argument("--refresh", action="store_true", help="ignora cache e rebaixa tudo")
    ap.add_argument("--cutoffs", default=",".join(str(c) for c in CORR_CUTOFFS_SENSITIVITY))
    ap.add_argument("--window-years", type=int, default=CORR_WINDOW_YEARS)
    ap.add_argument("--order-cad", type=float, default=ORDER_CAD)
    ap.add_argument("--friction-cap", type=float, default=FRICTION_CAP_PCT)
    ap.add_argument(
        "--common-currency",
        action="store_true",
        help="normaliza retornos para CAD via USDCAD (EXPERIMENTAL -- ver "
        "metodo.currency_normalization; NAO e o default)",
    )
    args = ap.parse_args()

    cutoffs = [float(c) for c in args.cutoffs.split(",") if c.strip()]
    primary_cutoff = CORR_CUTOFF_DEFAULT if CORR_CUTOFF_DEFAULT in cutoffs else cutoffs[0]

    log("=" * 78)
    log("build_effective_universe -- universo negociavel efetivo do SuperEzio")
    log("=" * 78)

    symbols = load_symbols()
    log(f"\n[1/6] lista de origem: {SRC_ETF_LIST}")
    log(f"      {len(symbols)} simbolos unicos (CAN+US+USA deduplicados)")

    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(OHLCV_DIR, exist_ok=True)

    log("\n[2/6] nomes factuais dos fundos")
    names = fetch_names(symbols, args.refresh)
    got = sum(1 for s in symbols if names.get(s["symbol"], {}).get("fund_name"))
    log(f"      fund_name obtido para {got}/{len(symbols)}")

    log(f"\n[3/6] historico OHLCV period=max -- {'REFRESH' if args.refresh else 'cache'}")
    dfs, errors, meta = {}, {}, {}
    for i, s in enumerate(symbols, 1):
        r = fetch_one(s["yahoo"], args.refresh)
        if r["df"] is None:
            errors[s["symbol"]] = r["error"]
            log(f"      [{i:3d}/{len(symbols)}] {s['symbol']:<9} ERRO: {r['error'][:80]}")
        else:
            dfs[s["symbol"]] = r["df"]
            meta[s["symbol"]] = {
                "yahoo_ticker": s["yahoo"],
                "bars": len(r["df"]),
                "start": str(r["df"].index.min().date()),
                "end": str(r["df"].index.max().date()),
                "data_source": r["source"],
            }
        if r["source"] == "yfinance":
            time.sleep(0.15)
    log(f"      {len(dfs)} com historico, {len(errors)} com erro literal")

    # USDCAD so entra se --common-currency for pedido (ver metodo.currency_normalization).
    fx, fx_note = None, "nao usado (medida primaria em moeda de listagem)"
    if args.common_currency:
        fx_res = fetch_one(FX_TICKER, args.refresh)
        if fx_res["df"] is not None:
            fx = fx_res["df"]["Close"].astype(float)
            fx_note = f"USDCAD ({FX_TICKER}) de {fx.index.min().date()} a {fx.index.max().date()}"
        else:
            fx_note = f"FALHOU: {fx_res['error']}"
        log(f"      cambio USDCAD (--common-currency): {fx_note}")

    currency = {s["symbol"]: s["currency"] for s in symbols}
    labels = {
        s["symbol"]: label_from_name(names.get(s["symbol"], {}).get("fund_name")) for s in symbols
    }
    idents = {
        s["symbol"]: fund_identity(names.get(s["symbol"], {}).get("fund_name")) for s in symbols
    }
    bars = {s: meta.get(s, {}).get("bars", 0) for s in labels}

    log(
        f"\n[4/6] correlacao -- retornos LOG diarios, janela {args.window_years} anos, "
        f"min_overlap={MIN_OVERLAP_BARS}"
    )
    frames = build_returns(
        dfs, currency, fx, args.window_years, common_currency=args.common_currency
    )
    corr, ov, rb = corr_matrices(frames, MIN_OVERLAP_BARS)
    if corr is None or corr.shape[0] < 2:
        log("      ERRO: sem dados suficientes para correlacionar")
        return 2
    log(
        f"      {corr.shape[0]} series na matriz, "
        f"{min(rb.values())}-{max(rb.values())} barras na janela"
    )

    def _sens(groups):
        cov = sorted(m for gg in groups for m in gg)
        return {
            "distinct_exposures": len(groups),
            "symbols_covered": len(cov),
            "singleton_clusters": sum(1 for x in groups if len(x) == 1),
            "fused_symbols": len(cov) - len(groups),
            "largest_cluster_size": max((len(x) for x in groups), default=0),
        }

    def _clusters(cut):
        return {
            "single_linkage": single_linkage_clusters(corr, ov, cut, MIN_OVERLAP_BARS),
            "single_linkage_plus_identity": add_identity_edges(
                single_linkage_clusters(corr, ov, cut, MIN_OVERLAP_BARS), idents
            ),
            "complete_linkage": complete_linkage_clusters(corr, ov, cut, MIN_OVERLAP_BARS),
            "complete_linkage_plus_identity": add_identity_edges(
                complete_linkage_clusters(corr, ov, cut, MIN_OVERLAP_BARS), idents
            ),
        }

    log("\n[5/6] clusters e sensibilidade")
    sensitivity = []
    for cut in sorted(cutoffs, reverse=True):
        c = _clusters(cut)
        row = {"cutoff": cut, **{k: _sens(v) for k, v in c.items()}}
        sensitivity.append(row)
        log(
            f"      corte {cut:.2f}  single={row['single_linkage']['distinct_exposures']:3d}  "
            f"single+ident={row['single_linkage_plus_identity']['distinct_exposures']:3d}  "
            f"complete={row['complete_linkage']['distinct_exposures']:3d}  "
            f"complete+ident={row['complete_linkage_plus_identity']['distinct_exposures']:3d}"
        )

    primary = _clusters(primary_cutoff)
    named = name_clusters(primary["complete_linkage_plus_identity"], labels, bars)
    clustered = {m for c in named for m in c["members"]}
    unclustered = sorted(set(labels) - clustered)

    log("\n[6/6] friccao, qualidade, elegibilidade")
    idents_multi = {}
    for s in symbols:
        f = idents[s["symbol"]]
        if f:
            idents_multi.setdefault(f, []).append(s["symbol"])
    same_fund_groups = {k: sorted(v) for k, v in idents_multi.items() if len(v) > 1}

    recs: dict[str, Any] = {}
    cluster_of = {m: c["cluster_id"] for c in named for m in c["members"]}

    for s in symbols:
        sym = s["symbol"]
        df = dfs.get(sym)
        fname = names.get(sym, {}).get("fund_name")
        zr = zero_return_pct(df) if df is not None else None
        stale = bool(zr is not None and zr > STALE_ZERO_RETURN_PCT)

        rec: dict[str, Any] = {
            "symbol": sym,
            "market": s["market"],
            "markets_in_source": s["markets"],
            "yahoo_ticker": s["yahoo"],
            "listing_currency": s["currency"],
            "fund_name": fname,
            "fund_identity": idents[sym],
            "same_fund_listings": sorted(same_fund_groups.get(idents[sym] or "", [sym])),
            "exposure_label": labels[sym],
            "correlation_cluster": cluster_of.get(sym),
            "bars_available": bands if (bands := bars.get(sym, 0)) else 0,
            "bars_in_corr_window": rb.get(sym),
            "history_start": meta.get(sym, {}).get("start"),
            "history_end": meta.get(sym, {}).get("end"),
            "data_quality": {
                "zero_return_days_pct_252": _r(zr, 2),
                "stale_series": stale,
                "stale_threshold_pct": STALE_ZERO_RETURN_PCT,
                "stale_note": (
                    "serie com >20% de pregoes sem variacao: preco defasado, "
                    "correlacao com ela nao e confiavel e o cluster pode estar errado"
                    if stale
                    else None
                ),
            },
        }
        if sym in errors:
            rec["data_error"] = errors[sym]
            rec["bars_available"] = 0

        # ---- friccao -------------------------------------------------------
        cs_med = cs_p90 = rng = None
        if df is not None and len(df) >= 21:
            recent = df.iloc[-252:]
            cs = corwin_schultz_spread(recent)
            cs_med, cs_p90 = median(cs), pct(cs, 0.9)
            rng = range_proxy(recent)

        cs_pct = cs_med * 100.0 if cs_med is not None else None
        cs_p90_pct = cs_p90 * 100.0 if cs_p90 is not None else None
        rng_pct = rng * 100.0 if rng is not None else None
        one_way = (cs_pct / 100.0) * args.order_cad if cs_pct is not None else None

        rec["friction"] = {
            "commission_pct": COMMISSION_PCT,
            "commission_note": "commission-free (TD Direct Investing) -> comissao = 0",
            "order_size_cad": args.order_cad,
            "order_size_note": (
                "ordem tipica: banca 1000 CAD, risco 1.0-1.5% por trade = 10-15 CAD; "
                "com stop na faixa de 3-5% do preco a ordem sai ~300 CAD"
            ),
            "spread_pct_corwin_schultz_median": _r(cs_pct, 4),
            "spread_pct_corwin_schultz_p90": _r(cs_p90_pct, 4),
            "spread_pct_range_upper_bound": _r(rng_pct, 4),
            "spread_is_estimate": True,
            "spread_estimate_note": (
                "ESTIMATIVA, nao spread observado de tela. Primario: estimador de "
                "Corwin & Schultz (2012, J. Finance) sobre high/low dos ultimos 252 "
                "pregoes -- unico estimador de bid-ask sem dado de quote. Secundario: "
                "mediana de (high-low)/close, que NAO e o spread e sim o range inteiro "
                "do dia, servindo so como teto conservador."
            ),
            "friction_pct_one_way": _r(cs_pct, 4),
            "friction_pct_round_trip": _r(cs_pct * 2 if cs_pct is not None else None, 4),
            "friction_cad_one_way": _r(one_way, 4),
            "friction_cad_round_trip": _r(one_way * 2 if one_way is not None else None, 4),
            "friction_cap_pct": args.friction_cap,
            "passes_friction_at_1000": bool(cs_pct is not None and cs_pct <= args.friction_cap),
            "passes_friction_round_trip": bool(
                cs_pct is not None and cs_pct * 2 <= args.friction_cap
            ),
            "passes_friction_range_upper_bound": bool(
                rng_pct is not None and rng_pct <= args.friction_cap
            ),
        }

        # ---- elegibilidade -------------------------------------------------
        n = bars.get(sym, 0)
        hist_ok, tech_ok = n >= MIN_BARS_TARGET, n >= MIN_BARS_TECHNICAL_NEURAL
        fr_ok = rec["friction"]["passes_friction_at_1000"]

        reasons = []
        if sym in errors:
            reasons.append(f"data_error ({errors[sym][:140]})")
        if not tech_ok:
            reasons.append(
                f"insufficient_history ({n} barras < {MIN_BARS_TECHNICAL_NEURAL} "
                f"minimo do technical_neural)"
            )
        elif not hist_ok:
            reasons.append(
                f"insufficient_history ({n} barras < alvo {MIN_BARS_TARGET}; "
                f"acima do minimo duro {MIN_BARS_TECHNICAL_NEURAL})"
            )
        if cs_pct is None:
            reasons.append("friction_unmeasurable (high/low insuficiente na janela)")
        elif not fr_ok:
            reasons.append(
                f"excessive_friction (spread estimado {cs_pct:.4f}% > "
                f"{args.friction_cap}% da ordem)"
            )

        rec["eligibility"] = {
            "min_bars_technical_neural": MIN_BARS_TECHNICAL_NEURAL,
            "target_bars": MIN_BARS_TARGET,
            "passes_history_minimum": tech_ok,
            "passes_history_target": hist_ok,
            "passes_friction": fr_ok,
        }
        rec["eligible"] = bool(hist_ok and fr_ok and tech_ok and sym not in errors)
        rec["eligible_strict"] = bool(rec["eligible"] and not stale)
        rec["reason_if_excluded"] = None if rec["eligible"] else "; ".join(reasons)
        rec["strict_exclusion_reason"] = (
            None
            if rec["eligible_strict"]
            else (rec["reason_if_excluded"] or f"stale_series ({zr:.1f}% de dias sem variacao)")
        )
        rec["caveat"] = _caveat(cs_pct, cs_p90_pct, rng_pct, args.friction_cap, stale, zr)
        recs[sym] = rec

    # ---- montagem do documento --------------------------------------------
    clusters_out = []
    for c in named:
        ms = c["members"]
        mic = min_intra_corr(ms, corr)
        clusters_out.append(
            {
                "cluster_id": c["cluster_id"],
                "size": len(ms),
                "members": ms,
                "representative": c["representative"],
                "base_label": c["base_label"],
                "labels_in_cluster": sorted({labels[m] for m in ms}),
                "fund_identities_in_cluster": sorted({idents[m] for m in ms if idents[m]}),
                "min_intra_correlation": _r(mic, 6),
                "cohesive": bool(mic is None or mic >= primary_cutoff),
                "chaining_warning": bool(len(ms) > 2 and mic is not None and mic < primary_cutoff),
                "chaining_note": (
                    "coesao abaixo do corte: nem todo par dentro do cluster chega a "
                    f"{primary_cutoff}. Cluster veio do eixo identidade-de-fundo ou de "
                    "encadeamento -- nao e uma exposicao unica."
                    if (len(ms) > 2 and mic is not None and mic < primary_cutoff)
                    else None
                ),
                "eligible_members": sorted(m for m in ms if recs[m]["eligible"]),
            }
        )

    distinct_combined = len(clusters_out)
    distinct_complete = len(primary["complete_linkage"])
    distinct_single = len(primary["single_linkage"])
    distinct_single_ident = len(primary["single_linkage_plus_identity"])
    distinct_ident = len({idents[s] for s in idents if idents[s]})

    # Diagnostico de cambio: pares que sao o MESMO indice em moedas diferentes.
    # Medido ao vivo, nao deduzido -- evidencia do limite da regra de 0.95.
    CROSS_CCY_PROBE = [
        ("VFV", "VOO", "S&P 500: VFV unhedged CAD x VOO USD"),
        ("VUN", "VTI", "EUA total market: VUN CAD x VTI USD"),
        ("VFV", "VSP", "S&P 500: VFV unhedged CAD x VSP hedged CAD"),
        ("SPY", "VOO", "S&P 500: SPY x VOO (mesma moeda, controle)"),
    ]
    cross_probe = []
    for a, b, why in CROSS_CCY_PROBE:
        if a in frames and b in frames:
            j = _pair_frame(frames[a], frames[b])
            if j is not None:
                cross_probe.append(
                    {
                        "pair": f"{a} x {b}",
                        "correlation": _r(j, 4),
                        "why": why,
                        "fuses_at_0.95": bool(j >= primary_cutoff),
                    }
                )

    elig = [s for s, r in recs.items() if r["eligible"]]
    elig_s = [s for s, r in recs.items() if r["eligible_strict"]]
    stale_list = [s for s, r in recs.items() if r["data_quality"]["stale_series"]]

    def split():
        h, f, b, o = [], [], [], []
        for s, r in recs.items():
            if r["eligible"]:
                continue
            why = r["reason_if_excluded"] or ""
            has_h = "insufficient_history" in why
            has_f = "excessive_friction" in why
            if has_h and has_f:
                b.append(s)
            elif has_h:
                h.append(s)
            elif has_f:
                f.append(s)
            else:
                o.append(s)
        return sorted(h), sorted(f), sorted(b), sorted(o)

    excl_h, excl_f, excl_both, excl_other = split()

    doc = {
        "schema_version": 1,
        "generated_at": now_utc(),
        "ttl_days": TTL_DAYS,
        "status": "generated",
        "artifact": "td_universe_effective",
        "purpose": (
            "Universo NEGOCIAVEL EFETIVO do protocolo $1000 CAD / taxa zero. Responde: "
            "quantas exposicoes distintas os 108 ETFs commission-free representam, "
            "quais passam na friccao <= 0.5% da ordem e quais tem historico suficiente "
            "para os experts."
        ),
        "cost": "custo zero -- yfinance (gratuito, sem cartao). Nada pago, nada cobrado.",
        "sources": {
            "symbol_universe": {
                "path": "config/td_direct_commission_free_etfs.json",
                "url": "https://www.td.com/ca/en/investing/direct-investing/commission-free-etfs",
                "verified_at": load_json(SRC_ETF_LIST).get("verified_at"),
            },
            "prices": {
                "provider": "yfinance",
                "yahoo_ticker_mapping": (
                    "CAN: '<SYM>.TO' com '.' -> '-' (TGED.U -> TGED-U.TO, BTCX.B -> "
                    "BTCX-B.TO). US/USA: ticker literal."
                ),
                "period": "max (period=max, interval=1d, auto_adjust=True)",
                "cache": "data/reference/effective_universe/ohlcv/<yahoo>.csv",
                "cost": "gratuito, sem cartao",
            },
            "fx": {
                "ticker": FX_TICKER,
                "note": fx_note,
                "cache": "data/reference/effective_universe/ohlcv/CAD_X.csv",
            },
            "fund_names": {
                "provider": "yfinance Ticker.info (longName/shortName)",
                "cache": "data/reference/effective_universe/fund_names.json",
                "used_for": "exposure_label e fund_identity (ver metodo)",
            },
            "technical_neural_not_used": (
                "data/reference/technical_neural/ NAO cobre nenhum dos 108 simbolos -- "
                "e amostra aleatoria de acoes do dataset AYUSHKHAIRE/"
                "all-stock-market-data-daily-updates. Verificado: 0 de 108 presentes. "
                "Por isso o historico vem do yfinance."
            ),
        },
        "method": {
            "correlation": (
                f"Pearson sobre retornos LOG diarios de Close ajustado (auto_adjust=True), "
                f"janela dos ultimos {args.window_years} anos (~{252 * args.window_years} "
                f"pregoes), par a par com min_periods={MIN_OVERLAP_BARS}."
            ),
            "currency_normalization": (
                "MEDIDA PRIMARIA: retornos na MOEDA DE LISTAGEM, sem conversao. E a "
                "leitura literal e reproduzivel da regra do projeto. LIMITE CONHECIDO: "
                "duas listagens do MESMO indice em moedas diferentes aparecem separadas "
                "porque a correlacao mede o cambio junto (medido: VFV x VOO = 0.9376 < "
                "0.95). Tentamos normalizar para CAD via USDCAD (--common-currency) e "
                "NAO resolveu: o USDCAD gratuito do Yahoo tem desalinhamento de "
                "timestamp com o fechamento das acoes -- a melhor correlacao entre "
                "(VFV-VOO) e o USDCAD fica em 0.71 mesmo testando deslocamento de +-2 "
                "dias, e a normalizacao PIOROU VFV x VOO (0.9376 -> 0.8866). Por isso "
                "a normalizacao ficou fora do caminho primario: sem fonte de cambio "
                "confiavel e gratuita, converter seria trocar um vies conhecido por um "
                "erro desconhecido. Ver headline.cross_currency_probe."
            ),
            "clustering": (
                "MEDIDA PRIMARIA: complete-linkage (coesao total) no corte "
                f"{primary_cutoff} -- dois grupos so se fundem se TODOS os pares "
                "cruzados estiverem >= corte. E o que responde 'quantas exposicoes "
                "distintas' sem mentir. SENSIBILIDADE: single-linkage, a leitura "
                "literal par-a-par da regra, que ENCADEIA (A~B, B~C, A!~C) e por isso "
                "funde grupos que NAO sao a mesma exposicao. A diferenca entre as duas "
                "e a medida do encadeamento -- ver headline.by_axis."
            ),
            "fund_identity_axis": (
                "Eixo INDEPENDENTE da correlacao: dois tickers com o mesmo fund_name "
                "sem o sufixo de moeda sao o MESMO fundo (classes de unidades CAD/USD, "
                "fato de prospectus). Entram como aresta de uniao. Isso captura pares "
                "que a correlacao perde quando a serie USD e iliquida/defasada."
            ),
            "exposure_label": (
                "Derivado do NOME FACTUAL do fundo (fund_name do Yahoo) por regras regex "
                "ordenadas por especificidade. Sem regra casando -> 'unclassified'. "
                "cluster_id vem do rotulo mais frequente entre os MEMBROS do cluster."
            ),
            "friction": (
                f"Comissao = 0 (lista commission-free) => friccao = spread. Spread "
                "ESTIMADO por Corwin & Schultz (2012, Journal of Finance) -- usa so "
                "high/low diarios, mediana dos ultimos 252 pregoes. Regra do protocolo: "
                f"comissao + spread <= {args.friction_cap}% da ordem."
            ),
            "spread_is_estimate": (
                "SIM, ESTIMATIVA. Nao ha NBBO historico em fonte gratuita sem cartao "
                "nesta maquina. O numero e um estimador publicado, nao uma observacao."
            ),
            "order_size": (
                f"{args.order_cad:.0f} CAD. Comissao 0 => custo em CAD = spread_pct x "
                "ordem. Como o corte e percentual, o tamanho da ordem cancela: "
                "passes_friction_at_1000 nao depende da banca."
            ),
            "eligibility": (
                f"eligible = (bars >= {MIN_BARS_TARGET}) AND (spread estimado <= "
                f"{args.friction_cap}%) AND (bars >= {MIN_BARS_TECHNICAL_NEURAL}) AND sem "
                "data_error. eligible_strict = eligible AND serie nao defasada "
                f"(<= {STALE_ZERO_RETURN_PCT}% de dias sem variacao)."
            ),
            "limits": [
                "O spread e estimativa de high/low (Corwin-Schultz), nao NBBO observado.",
                "Single-linkage encadeia -- ver chaining_warning em clusters.",
                (
                    "Classes .U da TSX sao pouco negociadas: a serie de preco fica "
                    "defasada e a correlacao com ela despenca mesmo sendo o mesmo fundo "
                    "da classe CAD."
                ),
                "Janela de 3 anos nao cobre 2008 nem 2020.",
                (
                    "MESMO INDICE, MOEDAS DIFERENTES nao funde por correlacao "
                    "(VFV x VOO = 0.9376). A regra de 0.95 nao distingue 'mesmo indice "
                    "em outra moeda' de 'ativo diferente' -- so a identidade de FUNDO "
                    "e capturada."
                ),
                (
                    "Fundos 'CAD Hedged' e a versao sem hedge do mesmo indice ficam em "
                    "clusters separados -- e correto do ponto de vista de risco cambial, "
                    "mas nao e o que a regra do projeto quer dizer com overlap."
                ),
            ],
        },
        "params": {
            "correlation_window_years": args.window_years,
            "correlation_cutoff": primary_cutoff,
            "correlation_cutoffs_sensitivity": sorted(cutoffs, reverse=True),
            "min_overlap_bars": MIN_OVERLAP_BARS,
            "min_bars_technical_neural": MIN_BARS_TECHNICAL_NEURAL,
            "target_bars": MIN_BARS_TARGET,
            "friction_cap_pct": args.friction_cap,
            "commission_pct": COMMISSION_PCT,
            "order_size_cad": args.order_cad,
            "stale_zero_return_pct": STALE_ZERO_RETURN_PCT,
        },
        "headline": {
            "symbols_in_source_list": len(symbols),
            "symbols_with_history": len(dfs),
            "symbols_with_data_error": len(errors),
            "distinct_exposure_count": distinct_combined,
            "distinct_exposure_count_definition": (
                f"clusters complete-linkage (coesao total, sem encadeamento) @ "
                f"{primary_cutoff} sobre retornos LOG diarios em moeda de listagem, "
                "unidos por IDENTIDADE DE FUNDO (mesmo fundo em classes CAD/USD). "
                "Todo simbolo da lista entra na conta -- sem cluster proprio = cluster de 1."
            ),
            "by_axis": {
                "complete_linkage_primary": distinct_complete,
                "complete_linkage_plus_fund_identity": distinct_combined,
                "single_linkage_literal_rule": distinct_single,
                "single_linkage_plus_fund_identity": distinct_single_ident,
                "fund_identity_only": distinct_ident,
                "chaining_inflation_single_vs_complete": distinct_single - distinct_complete,
                "note": (
                    "single_linkage_literal_rule > complete_linkage_primary: a leitura "
                    "par-a-par da regra de 0.95 ENCADEIA e funde grupos que nao sao a "
                    "mesma exposicao. A diferenca mede o tamanho da ilusao de overlap."
                ),
            },
            "cross_currency_probe": {
                "what": (
                    "mesmo indice economico, moedas de listagem diferentes -- medido ao "
                    "vivo para dimensionar o limite da regra de 0.95"
                ),
                "pairs": cross_probe,
            },
            "symbols_not_clustered": len(unclustered),
            "symbols_not_clustered_list": unclustered,
            "same_fund_groups": same_fund_groups,
            "same_fund_group_count": len(same_fund_groups),
            "overlap_ratio": _r(
                len(clustered) / distinct_combined if distinct_combined else None, 3
            ),
            "eligible_count": len(elig),
            "eligible_strict_count": len(elig_s),
            "stale_series_count": len(stale_list),
            "stale_series_list": sorted(stale_list),
            "excluded_insufficient_history_only": len(excl_h),
            "excluded_excessive_friction_only": len(excl_f),
            "excluded_both_causes": len(excl_both),
            "excluded_other": len(excl_other),
            "eligible_symbols": sorted(elig),
            "eligible_strict_symbols": sorted(elig_s),
            "excluded_insufficient_history_nominal": excl_h,
            "excluded_excessive_friction_nominal": excl_f,
            "excluded_both_causes_nominal": excl_both,
            "excluded_other_nominal": excl_other,
            "sensitivity": sensitivity,
        },
        "clusters": clusters_out,
        "symbols": {k: recs[k] for k in sorted(recs)},
        "data_errors": errors,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------- relatorio
    log("")
    log("=" * 78)
    log("RESULTADO")
    log("=" * 78)
    log(f"  {len(symbols)} simbolos na lista de origem")
    log(
        f"  = {distinct_combined} EXPOSICOES DISTINTAS   (corte {primary_cutoff}, "
        "coesao total + identidade de fundo)"
    )
    if distinct_combined == len(symbols):
        log("  !! distinct == len(symbols): NADA fundiu. O corte pode estar frouxo.")
    log("")
    log("  leituras do MESMO dado, por eixo (a diferenca e o resultado):")
    log(f"    complete-linkage (primario, sem encadear)   : {distinct_complete}")
    log(f"    complete-linkage + identidade de fundo      : {distinct_combined}")
    log(f"    single-linkage (regra literal par-a-par)    : {distinct_single}")
    log(f"    single-linkage + identidade de fundo        : {distinct_single_ident}")
    log(f"    identidade de fundo apenas                  : {distinct_ident}")
    log(
        f"    inflacao por ENCADEAMENTO no single-linkage : "
        f"{distinct_single - distinct_complete} grupos fundidos indevidamente"
    )
    log("")
    log("  pares de MESMO indice em moedas diferentes (limite da regra de 0.95):")
    for p in cross_probe:
        log(
            f"    {p['pair']:<14} corr={p['correlation']:.4f}  "
            f"funde@0.95={'SIM' if p['fuses_at_0.95'] else 'NAO'}  -- {p['why']}"
        )
    log("")
    log(f"  {'cluster':<28} {'n':>3}  {'minIntra':>8}  membros")
    log(f"  {'-' * 28} {'-' * 3}  {'-' * 8}  {'-' * 40}")
    for c in sorted(clusters_out, key=lambda x: (-x["size"], x["cluster_id"])):
        ms = c["members"]
        ex = ", ".join(ms[:6]) + (f" ... (+{len(ms) - 6})" if len(ms) > 6 else "")
        warn = " [CHAIN]" if c["chaining_warning"] else ""
        mi = (
            f"{c['min_intra_correlation']:.3f}"
            if c["min_intra_correlation"] is not None
            else "   -"
        )
        log(f"  {c['cluster_id']:<28} {c['size']:>3}  {mi:>8}  {ex}{warn}")
    log("")
    log(f"  clusters de 1 simbolo: {sum(1 for c in clusters_out if c['size'] == 1)}")
    log(
        f"  clusters com ENCADEAMENTO (min_intra < {primary_cutoff}): "
        f"{[c['cluster_id'] for c in clusters_out if c['chaining_warning']]}"
    )
    log("")
    log(f"  elegiveis (historico>=1000 E friccao<=0.5%): {len(elig)}/{len(symbols)}")
    log(f"  elegiveis estritos (tambem serie nao defasada): {len(elig_s)}/{len(symbols)}")
    log(f"    excluidos por HISTORICO apenas : {len(excl_h)}")
    for s in excl_h:
        log(f"        {s:<9} {recs[s]['reason_if_excluded']}")
    log(f"    excluidos por FRICCAO apenas   : {len(excl_f)}")
    for s in excl_f:
        log(f"        {s:<9} {recs[s]['reason_if_excluded']}")
    log(f"    excluidos por AMBAS as causas  : {len(excl_both)} -> {excl_both}")
    if excl_other:
        log(f"    excluidos por outro motivo     : {len(excl_other)} -> {excl_other}")
    log("")
    log(f"  series DEFASADAS (>20% dias sem variacao), correlacao nao confiavel: {len(stale_list)}")
    for s in sorted(stale_list):
        log(
            f"        {s:<9} {recs[s]['data_quality']['zero_return_days_pct_252']:>5.1f}% "
            f"de dias sem variacao | cluster={recs[s]['correlation_cluster']}"
        )
    log("")
    log("  sensibilidade do corte de correlacao:")
    log(f"    {'corte':>6}  {'single':>7}  {'single+id':>10}  {'complete':>9}  {'complete+id':>12}")
    for row in sensitivity:
        log(
            f"    {row['cutoff']:>6.2f}  {row['single_linkage']['distinct_exposures']:>7}  "
            f"{row['single_linkage_plus_identity']['distinct_exposures']:>10}  "
            f"{row['complete_linkage']['distinct_exposures']:>9}  "
            f"{row['complete_linkage_plus_identity']['distinct_exposures']:>12}"
        )
    log("")
    log(f"  escrito: {OUT_JSON}")
    log("=" * 78)
    return 0


def _caveat(cs_pct, cs_p90, rng, cap, stale, zr):
    notes = []
    if stale:
        notes.append(
            f"serie defasada ({zr:.1f}% dos dias sem variacao) -- cluster e "
            "friccao desta linha sao pouco confiaveis"
        )
    if cs_pct is not None and cs_p90 is not None and cs_p90 > cap >= cs_pct:
        notes.append(
            f"passa pela mediana ({cs_pct:.4f}%) mas o p90 do estimador "
            f"({cs_p90:.4f}%) estoura o teto: friccao instavel"
        )
    if rng is not None and cs_pct is not None and cs_pct > 0 and rng > 4 * cs_pct:
        notes.append(
            f"range diario ({rng:.3f}%) >> spread estimado ({cs_pct:.4f}%): "
            "volatilidade real ou estimador subestimando"
        )
    return "; ".join(notes) if notes else None


if __name__ == "__main__":
    sys.exit(main())
