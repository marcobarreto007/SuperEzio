#!/usr/bin/env python
"""verify_effective_universe.py -- verificador do universo negociavel efetivo.

Confere `config/td_universe_effective.json` contra a lista de origem
`config/td_direct_commission_free_etfs.json`. NAO confia no JSON: recomputa os
conjuntos a partir da origem.

Checagens DURAS (falham, exit != 0):
  D1  os 108 simbolos da origem estao todos no JSON, e nada a mais
  D2  todo simbolo tem `correlation_cluster` nao nulo
  D3  os clusters sao uma PARTICao: sem membro duplicado, sem membro orfao,
      `size` == len(members), e `symbols[s].correlation_cluster` == cluster_id
  D4  len(clusters) == headline.distinct_exposure_count
  D5  toda exclusao tem motivo nao vazio E bate com os portoes que falharam
  D6  as contagens fecham: elegiveis + 4 causas de exclusao == 108
  D7  sensibilidade nao aumenta quando o corte afrouxa
  D8  friccao: elegivel <= 0.5% ; excluido por friccao > 0.5%
  D9  historico: elegivel >= 1000 barras ; excluido so por historico < 1000

Checagens MOLES (viram AVISO, nao derrubam): cluster de 1 membro suspeito --
mesmo fundo em dois clusters, ou dois clusters com o mesmo rotulo de exposicao.

Uso:
    python scripts/verify_effective_universe.py
    python scripts/verify_effective_universe.py --json-relatorio saida.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ETF_LIST = os.path.join(ROOT, "config", "td_direct_commission_free_etfs.json")
EFFECTIVE = os.path.join(ROOT, "config", "td_universe_effective.json")

REQUIRED_TOP = [
    "schema_version",
    "generated_at",
    "ttl_days",
    "status",
    "sources",
    "headline",
    "clusters",
    "symbols",
]

_SUFFIX_RE = re.compile(r"_\d+$")


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def source_symbols(doc: Any) -> list[str]:
    """Lista de simbolos da origem, preservando aparicao e unicidade."""
    out: list[str] = []
    seen: set[str] = set()
    markets = doc.get("symbols") or {}
    for market in sorted(markets):
        for sym in markets[market] or []:
            if sym not in seen:
                seen.add(sym)
                out.append(sym)
    return out


class Report:
    def __init__(self) -> None:
        self.fail: list[str] = []
        self.warn: list[str] = []
        self.checks: list[tuple[str, str, str]] = []

    def ok(self, tag: str, msg: str) -> None:
        self.checks.append((tag, "OK", msg))

    def fail_check(self, tag: str, msg: str) -> None:
        self.checks.append((tag, "FALHA", msg))
        self.fail.append(f"[{tag}] {msg}")

    def warn_check(self, tag: str, msg: str) -> None:
        self.checks.append((tag, "AVISO", msg))
        self.warn.append(f"[{tag}] {msg}")


def check_partition(doc: Any, symbols: dict, rep: Report) -> dict[str, list[str]]:
    clusters = doc["clusters"]
    membership: dict[str, str] = {}
    duplicated: list[str] = []
    for cl in clusters:
        cid = cl["cluster_id"]
        members = cl["members"]
        if cl.get("size") != len(members):
            rep.fail_check("D3", f"cluster {cid}: size={cl.get('size')} != {len(members)} membros")
        if not members:
            rep.fail_check("D3", f"cluster {cid} esta vazio")
        for s in members:
            if s in membership:
                duplicated.append(f"{s} (em {membership[s]} e {cid})")
            membership[s] = cid
    if duplicated:
        rep.fail_check("D3", f"simbolos em mais de um cluster: {sorted(set(duplicated))}")

    orphans = sorted(set(symbols) - set(membership))
    ghosts = sorted(set(membership) - set(symbols))
    if orphans:
        rep.fail_check("D3", f"simbolos sem cluster nenhum: {orphans}")
    if ghosts:
        rep.fail_check("D3", f"membros de cluster que nao estao em symbols: {ghosts}")

    mismatched = [
        s for s, cid in membership.items() if symbols[s].get("correlation_cluster") != cid
    ]
    if mismatched:
        rep.fail_check(
            "D3",
            "symbols[s].correlation_cluster != cluster que o contem: " + str(sorted(mismatched)),
        )
    if not (duplicated or orphans or ghosts or mismatched):
        rep.ok("D3", f"particao valida: {len(membership)} simbolos em {len(clusters)} clusters")
    return membership


def check_exclusion_reasons(symbols: dict, rep: Report) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        "insufficient_history": [],
        "excessive_friction": [],
        "both": [],
        "other": [],
        "eligible": [],
    }
    for sym, rec in sorted(symbols.items()):
        elig = bool(rec.get("eligible"))
        reason = (rec.get("reason_if_excluded") or "").strip()
        eg = rec.get("eligibility") or {}
        target_ok = bool(eg.get("passes_history_target"))
        tech_ok = bool(eg.get("passes_history_minimum"))
        fr_ok = bool(eg.get("passes_friction"))
        has_err = bool(rec.get("data_error"))
        if elig:
            if reason:
                rep.fail_check("D5", f"{sym}: eligible=true mas tem reason_if_excluded='{reason}'")
            if not (target_ok and fr_ok and tech_ok) or has_err:
                rep.fail_check(
                    "D5",
                    f"{sym}: eligible=true com portao falhando "
                    f"(alvo={target_ok} friccao={fr_ok} minimo={tech_ok} erro={has_err})",
                )
            buckets["eligible"].append(sym)
            continue
        if not reason:
            rep.fail_check("D5", f"{sym}: eligible=false e SEM motivo registrado")
            buckets["other"].append(sym)
            continue
        if target_ok and tech_ok and fr_ok and not has_err:
            rep.fail_check("D5", f"{sym}: marcado excluido ('{reason}') mas nenhum portao falhou")
        failing = []
        if not tech_ok or not target_ok:
            failing.append("hist")
        if not fr_ok:
            failing.append("friccao")
        if has_err:
            failing.append("erro")
        key = {
            ("hist",): "insufficient_history",
            ("friccao",): "excessive_friction",
            ("hist", "friccao"): "both",
        }.get(tuple(failing), "other")
        if key == "other" and reason.startswith(("friction_unmeasurable", "data_error")):
            key = "other"
        buckets[key].append(sym)
        # o motivo nominal tem de citar a causa que realmente falhou
        if key == "insufficient_history" and "insufficient_history" not in reason:
            rep.fail_check("D5", f"{sym}: falha historico mas motivo nao diz: '{reason}'")
        if key == "excessive_friction" and "excessive_friction" not in reason:
            rep.fail_check("D5", f"{sym}: falha friccao mas motivo nao diz: '{reason}'")
        if key == "both" and not (
            "insufficient_history" in reason and "excessive_friction" in reason
        ):
            rep.fail_check("D5", f"{sym}: falham ambas mas motivo incompleto: '{reason}'")
    if not rep.fail:
        rep.ok("D5", f"todos os {len(symbols)} simbolos tem motivo coerente com os portoes")
    return buckets


def check_counts(doc: Any, buckets: dict[str, list[str]], rep: Report) -> None:
    h = doc["headline"]
    total = len(doc["symbols"])
    expect = {
        "excluded_insufficient_history_only": len(buckets["insufficient_history"]),
        "excluded_excessive_friction_only": len(buckets["excessive_friction"]),
        "excluded_both_causes": len(buckets["both"]),
        "excluded_other": len(buckets["other"]),
        "eligible_count": len(buckets["eligible"]),
    }
    bad = [f"{k}: JSON={h.get(k)} real={v}" for k, v in expect.items() if h.get(k) != v]
    if bad:
        rep.fail_check("D6", "contagens divergem -- " + "; ".join(bad))
    soma = sum(expect.values())
    if soma != total:
        rep.fail_check("D6", f"soma dos baldes = {soma} != {total} simbolos")
    if not bad and soma == total:
        rep.ok(
            "D6",
            f"{total} = {expect['eligible_count']} elegiveis + "
            f"{expect['excluded_insufficient_history_only']} historico + "
            f"{expect['excluded_excessive_friction_only']} friccao + "
            f"{expect['excluded_both_causes']} ambas + {expect['excluded_other']} outros",
        )
    nominal = {
        "excluded_insufficient_history_nominal": set(buckets["insufficient_history"]),
        "excluded_excessive_friction_nominal": set(buckets["excessive_friction"]),
        "eligible_symbols": set(buckets["eligible"]),
    }
    for key, want in nominal.items():
        got = set(h.get(key) or [])
        if got != want:
            rep.fail_check(
                "D6", f"{key} nao bate: faltam={sorted(want - got)} sobram={sorted(got - want)}"
            )


def check_sensitivity(doc: Any, rep: Report) -> None:
    rows = doc["headline"].get("sensitivity") or []
    if not rows:
        rep.warn_check("D7", "sem tabela de sensibilidade no JSON")
        return
    axes = ["single_linkage", "single_linkage_plus_identity", "complete_linkage"]
    axes.append("complete_linkage_plus_identity")
    problems: list[str] = []
    for axis in axes:
        seq = [(r["cutoff"], (r.get(axis) or {}).get("distinct_exposures")) for r in rows]
        seq = [(c, v) for c, v in seq if v is not None]
        seq.sort(key=lambda t: -t[0])
        for (c_hi, v_hi), (c_lo, v_lo) in itertools.pairwise(seq):
            if v_lo > v_hi:
                problems.append(
                    f"{axis}: corte {c_hi}->{c_lo} exposicoes {v_hi}->{v_lo} (aumentou)"
                )
    if problems:
        rep.fail_check("D7", "; ".join(problems))
    else:
        rep.ok("D7", f"monotona em {len(axes)} eixos e {len(rows)} cortes")


def check_gates(doc: Any, rep: Report) -> None:
    cap = float((doc.get("params") or {}).get("friction_cap_pct") or 0.5)
    target = int((doc.get("params") or {}).get("target_bars") or 1000)
    fr_bad: list[str] = []
    hi_bad: list[str] = []
    for sym, rec in sorted(doc["symbols"].items()):
        fr = rec.get("friction") or {}
        spread = fr.get("spread_pct_corwin_schultz_mean")
        eg = rec.get("eligibility") or {}
        passes = fr.get("passes_friction_at_1000")
        if spread is not None and passes is not None and bool(passes) != (float(spread) <= cap):
            fr_bad.append(f"{sym}={spread}% passes={passes}")
        if spread is None and eg.get("passes_friction"):
            fr_bad.append(f"{sym}: passes_friction=true sem spread medido")
        bars = rec.get("bars_available")
        if rec.get("eligible") and bars is not None and int(bars) < target:
            hi_bad.append(f"{sym}={bars}<{target}")
        if eg.get("passes_history_target") and bars is not None and int(bars) < target:
            hi_bad.append(f"{sym}=passes_history_target com {bars} barras < {target}")
    if fr_bad:
        rep.fail_check("D8", "flag de friccao incoerente com o valor medido: " + "; ".join(fr_bad))
    else:
        rep.ok("D8", f"friccao coerente com o teto de {cap}% em todos os simbolos medidos")
    if hi_bad:
        rep.fail_check("D9", "flag de historico incoerente: " + "; ".join(hi_bad))
    else:
        rep.ok("D9", f"historico coerente com o alvo de {target} barras")


def check_singletons(doc: Any, membership: dict[str, str], rep: Report) -> None:
    """Cluster de 1 membro errado. NAO derruba: reporta nominalmente.

    M1 = MESMO FUNDO em clusters diferentes -> isso e defeito, fundo identico nao
         pode estar em dois lugares (a regra de 0.95 + eixo de identidade deveriam
         ter fundido). Só pode ser zero.
    M4 = MESMO ROTULO DE EXPOSICAO em clusters diferentes -> NAO e defeito: sao
         fundos DIFERENTES da mesma categoria cuja correlacao ficou abaixo do corte.
         E um achado (o corte de 0.95 nao junta a categoria), reportado agrupado.
    """
    clusters = doc["clusters"]
    by_ident: dict[str, list[str]] = {}
    by_label: dict[str, list[str]] = {}
    for cl in clusters:
        cid = cl["cluster_id"]
        for ident in cl.get("fund_identities_in_cluster") or []:
            by_ident.setdefault(ident, []).append(cid)
        label = _SUFFIX_RE.sub("", cl.get("base_label") or cid)
        by_label.setdefault(label, []).append(cid)

    singles = {cl["cluster_id"]: cl["members"][0] for cl in clusters if cl.get("size") == 1}

    # M1 -- defeito duro: mesmo fundo partido em dois clusters
    partidos: list[str] = []
    for cid, cids in sorted(by_ident.items()):
        if len(cids) > 1:
            membros = [s for cl in clusters if cl["cluster_id"] in cids for s in cl["members"]]
            partidos.append(f"fundo '{cid}' em {cids} -> {sorted(membros)}")
    for cid, sym in sorted(singles.items()):
        rec = doc["symbols"][sym]
        ident = rec.get("fund_identity") or ""
        outros = [c for c in by_ident.get(ident, []) if c != cid]
        if outros:
            partidos.append(f"{sym} ({cid}): MESMO FUNDO tambem em {outros}")
    if partidos:
        rep.warn_check("M1", f"{len(partidos)} caso(s) de MESMO FUNDO em clusters separados:")
        for p in partidos:
            rep.warn_check("M1", "   " + p)
    else:
        rep.ok(
            "M1",
            f"{len(singles)} clusters de 1 membro e nenhum fundo partido em dois clusters "
            f"({len(by_ident)} identidades de fundo distintas)",
        )

    # M4 -- achado: mesma categoria de exposicao em clusters separados
    repetidos = {lab: cids for lab, cids in by_label.items() if len(cids) > 1}
    if repetidos:
        n_sym = 0
        for lab, cids in sorted(repetidos.items()):
            membros = sorted(
                s for cl in clusters if cl["cluster_id"] in cids for s in cl["members"]
            )
            n_sym += len(membros)
            rep.warn_check(
                "M4",
                f"rotulo '{lab}' em {len(cids)} clusters ({len(membros)} simbolos): {membros}",
            )
        rep.warn_check(
            "M4",
            f"{len(repetidos)} rotulo(s) repetido(s) em {n_sym} simbolos -- fundos DIFERENTES da "
            "mesma categoria que o corte de 0.95 NAO fundiu (achado, nao defeito)",
        )
    else:
        rep.ok("M4", "nenhum rotulo de exposicao repetido entre clusters")

    sem_coesao = [cl["cluster_id"] for cl in clusters if cl.get("cohesion_warning")]
    faltando = [
        cl["cluster_id"]
        for cl in clusters
        if cl.get("cohesion_warning") and not (cl.get("cohesion_warning_cause") or "").strip()
    ]
    if faltando:
        rep.fail_check("M2", f"cluster com aviso de coesao e SEM causa: {faltando}")
    else:
        rep.ok("M2", f"{len(sem_coesao)} cluster(s) com aviso de coesao, todos com causa declarada")

    stale = [
        s for s, r in doc["symbols"].items() if (r.get("data_quality") or {}).get("stale_series")
    ]
    if stale:
        rep.warn_check(
            "M3", f"{len(stale)} series DEFASADAS (>20% dias sem variacao): {sorted(stale)}"
        )
    else:
        rep.ok("M3", "nenhuma serie defasada")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica o universo negociavel efetivo.")
    ap.add_argument("--json-relatorio", default=None, help="grava o relatorio em JSON")
    args = ap.parse_args()

    rep = Report()
    if not os.path.exists(EFFECTIVE):
        print(f"FALHA: nao existe {EFFECTIVE}")
        return 2
    doc = load_json(EFFECTIVE)
    src = load_json(SRC_ETF_LIST)

    faltando_top = [k for k in REQUIRED_TOP if k not in doc]
    if faltando_top:
        rep.fail_check("D0", f"campos obrigatorios ausentes no JSON: {faltando_top}")
    else:
        rep.ok("D0", f"schema presente: {', '.join(REQUIRED_TOP)}")

    src_syms = source_symbols(src)
    json_syms = sorted(doc["symbols"])
    missing = sorted(set(src_syms) - set(json_syms))
    extra = sorted(set(json_syms) - set(src_syms))
    if missing:
        rep.fail_check("D1", f"simbolos da origem ausentes no JSON: {missing}")
    if extra:
        rep.fail_check("D1", f"simbolos no JSON que nao existem na origem: {extra}")
    if len(src_syms) != 108:
        rep.fail_check("D1", f"a origem tem {len(src_syms)} simbolos unicos, esperado 108")
    if not (missing or extra):
        rep.ok("D1", f"{len(src_syms)} simbolos da origem == {len(json_syms)} no JSON")

    nulos = [
        s for s, r in doc["symbols"].items() if not (r.get("correlation_cluster") or "").strip()
    ]
    if nulos:
        rep.fail_check("D2", f"simbolos sem correlation_cluster: {sorted(nulos)}")
    else:
        rep.ok("D2", f"todos os {len(json_syms)} simbolos tem correlation_cluster")

    membership = check_partition(doc, doc["symbols"], rep)

    n_cl = len(doc["clusters"])
    n_head = doc["headline"].get("distinct_exposure_count")
    if n_cl != n_head:
        rep.fail_check("D4", f"len(clusters)={n_cl} != distinct_exposure_count={n_head}")
    else:
        rep.ok("D4", f"{n_cl} clusters == headline.distinct_exposure_count")

    buckets = check_exclusion_reasons(doc["symbols"], rep)
    check_counts(doc, buckets, rep)
    check_sensitivity(doc, rep)
    check_gates(doc, rep)
    check_singletons(doc, membership, rep)

    w = 6
    print("=" * 78)
    print("VERIFICADOR DO UNIVERSO NEGOCIAVEL EFETIVO")
    print(f"  origem : {SRC_ETF_LIST}")
    print(f"  alvo   : {EFFECTIVE}")
    print(f"  gerado : {doc.get('generated_at')}  (ttl {doc.get('ttl_days')} dias)")
    print("=" * 78)
    for tag, status, msg in rep.checks:
        print(f"  [{tag:<{w}}] {status:<5} {msg}")
    print("-" * 78)
    h = doc["headline"]
    print(f"  simbolos na origem          : {h.get('symbols_in_source_list')}")
    print(f"  clusters (exposicoes)       : {n_cl}")
    print(f"  elegiveis                   : {h.get('eligible_count')}")
    print(f"  excluidos por historico     : {h.get('excluded_insufficient_history_only')}")
    print(f"  excluidos por friccao       : {h.get('excluded_excessive_friction_only')}")
    print(f"  excluidos por ambas         : {h.get('excluded_both_causes')}")
    print("-" * 78)
    if rep.fail:
        print(f"RESULTADO: FALHOU -- {len(rep.fail)} checagem(ns) dura(s) vermelha(s)")
        for f in rep.fail:
            print("   " + f)
    else:
        print(f"RESULTADO: PASSOU -- todas as checagens duras verdes ({len(rep.warn)} aviso(s))")
    print("=" * 78)

    if args.json_relatorio:
        with open(args.json_relatorio, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "passed": not rep.fail,
                    "failures": rep.fail,
                    "warnings": rep.warn,
                    "checks": [{"tag": t, "status": s, "msg": m} for t, s, m in rep.checks],
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
        print(f"relatorio: {args.json_relatorio}")
    return 1 if rep.fail else 0


if __name__ == "__main__":
    sys.exit(main())
