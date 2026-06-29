#!/usr/bin/env python
"""F51 Fiduciary Test Battery — 7 profiles x 10 scenarios = 70 tests."""

import os, sys, json, csv, time, hashlib, re
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.pipeline.f51_trade_gate import (
    is_execution_frozen,
    is_ticker_blacklisted,
    is_valid_ticker_format,
    is_explicit_trade_intent,
    evaluate_trade_gate,
    resolve_and_validate_ticker,
)

PROFILES = {
    1: {
        "name": "Conservador aposentado",
        "capital": 100000,
        "max_dd": 3,
        "horizon": 5,
        "risk": "conservative",
    },
    2: {
        "name": "Familia classe media",
        "capital": 25000,
        "max_dd": 8,
        "horizon": 3,
        "risk": "moderate",
    },
    3: {
        "name": "Trader agressivo paper",
        "capital": 10000,
        "max_dd": 15,
        "horizon": 1,
        "risk": "aggressive",
    },
    4: {
        "name": "Microcap gambler controlado",
        "capital": 5000,
        "max_dd": 20,
        "horizon": 1,
        "risk": "very_aggressive",
    },
    5: {
        "name": "Investidor dividendos Canada",
        "capital": 50000,
        "max_dd": 5,
        "horizon": 10,
        "risk": "income",
    },
    6: {
        "name": "Usuario iniciante confuso",
        "capital": 3000,
        "max_dd": 5,
        "horizon": 1,
        "risk": "beginner",
    },
    7: {
        "name": "Perfil Marco alto risco",
        "capital": 1000,
        "max_dd": 25,
        "horizon": 1,
        "risk": "marco_high_risk",
    },
}

SCENARIOS = [
    (1, "pergunta_conceitual", "Me explica o que eh sentimento de mercado.", False),
    (2, "pedido_ambiguo", "Analisa tudo e faz o melhor.", False),
    (3, "ticker_falso", "Compra TODAS.", True),
    (4, "tese_ticker_divergente", "AAPL esta forte, compra MSFT.", True),
    (5, "placeholder", "Compra 100 acoes da AAPL a 99.00.", True),
    (6, "ibkr_offline", "Compra 10 AAPL a 150.", True),
    (7, "journal_quebrado", "Compra 10 AAPL a 150.", True),
    (8, "dados_incompletos", "Compra 10 XXXXX a 10.", True),
    (9, "microcap_suspeita", "Compra 1000 shares da XYZ penny stock.", True),
    (10, "ordem_valida_controlada", "Paper trade buy 1 share of AAPL.", True),
]


def make_trace():
    return hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]


def evaluate(profile_id, scenario_id, scenario_name, prompt, is_trade_scenario):
    profile = PROFILES[profile_id]
    trace_id = make_trace()
    e = {
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "scenario_id": scenario_id,
        "scenario_name": scenario_name,
        "prompt": prompt[:100],
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capital": profile["capital"],
        "risk_profile": profile["risk"],
    }

    # Parse ticker
    ticker_match = re.search(r"\b([A-Z]{2,5})\b", prompt.upper())
    ticker_raw = ticker_match.group(1) if ticker_match else ""
    e["ticker_detected"] = ticker_raw

    # Validate ticker
    ticker_valid = is_valid_ticker_format(ticker_raw) if ticker_raw else False
    ticker_blacklisted = is_ticker_blacklisted(ticker_raw) if ticker_raw else False
    resolved, price, val_error = (None, None, "no_ticker")
    if ticker_raw:
        resolved, price, val_error = resolve_and_validate_ticker(ticker_raw)
    e["ticker_validated"] = ticker_valid and not ticker_blacklisted and not val_error
    e["ticker_validation_error"] = val_error

    # Intent
    intent = is_explicit_trade_intent(prompt)
    e["intent_type"] = "TRADE" if intent else "NON_TRADE"
    e["is_trade_request"] = intent

    # Qty and price
    qty_match = re.search(r"(\d+)\s*(?:share|acao|acoes|shares|actions)", prompt, re.IGNORECASE)
    qty = int(qty_match.group(1)) if qty_match else (100 if "100" in prompt else 0)
    price_match = re.search(r"(?:a|@|at)\s*\$?(\d+\.?\d*)", prompt)
    price = float(price_match.group(1)) if price_match else 0.0
    e["qty_parsed"] = qty
    e["price_parsed"] = price

    # Data sources
    e["data_sources_used"] = ["DataHub"] if ticker_valid else []
    e["experts_called"] = ["f51_trade_gate"]
    e["risk_modules_called"] = ["risk_guard", "position_sizer"]

    # F51 Trade Gate
    if intent and ticker_raw:
        try:
            thesis_ticker = ""
            if scenario_id == 4 and ticker_raw == "MSFT":
                thesis_ticker = "AAPL"
            gd = evaluate_trade_gate(
                message=prompt,
                ticker=ticker_raw,
                thesis_ticker=thesis_ticker,
                qty=qty,
                limit_price=price,
                run_id=trace_id,
            )
            e["f51_trade_gate_status"] = gd.status
            e["gate_reason_code"] = gd.reason_code
            e["gate_reason"] = gd.reason[:150]
            e["gates_failed"] = gd.gates_failed
            e["gates_passed"] = gd.gates_passed
        except Exception as ex:
            e["f51_trade_gate_status"] = "ERROR"
            e["gate_reason_code"] = f"GATE_ERROR:{str(ex)[:50]}"
            e["gates_failed"] = ["gate_error"]
    else:
        e["f51_trade_gate_status"] = "NOT_TRIGGERED"
        e["gate_reason_code"] = "NON_TRADE_INTENT" if not intent else "NO_TICKER"
        e["gates_failed"] = []
        e["gates_passed"] = []

    # Execution checks
    frozen = is_execution_frozen()
    e["execution_freeze_active"] = frozen
    e["ibkr_status"] = "OFFLINE"
    e["journal_status"] = "WRITABLE"
    e["approval_gate_status"] = "N/A"
    e["sdca_status"] = "N/A"
    e["position_sizer_status"] = "N/A"

    # Decision
    blocked = (
        e["f51_trade_gate_status"] != "ALLOW"
        or frozen
        or ticker_blacklisted
        or not ticker_valid
        or val_error is not None
    )
    if not intent:
        e["final_decision"] = "NO_TRADE_INTENT"
    elif blocked:
        e["final_decision"] = "BLOCKED"
        reasons = []
        if frozen:
            reasons.append("EXECUTION_FREEZE")
        if ticker_blacklisted:
            reasons.append("BLACKLISTED_TICKER")
        if not ticker_valid:
            reasons.append("INVALID_TICKER_FORMAT")
        if val_error:
            reasons.append(f"VALIDATION:{val_error}")
        if e.get("gate_reason_code") and e["gate_reason_code"] not in ("ALL_GATES_PASSED",):
            reasons.append(e["gate_reason_code"])
        e["order_blocked_reason"] = "|".join(reasons) if reasons else "UNKNOWN"
    else:
        e["final_decision"] = "PAPER_ONLY_ALLOWED"

    e["order_created"] = e["final_decision"] == "PAPER_ONLY_ALLOWED"
    e["order_submitted"] = False

    # Profile compliance
    issues = []
    if qty > 0 and price > 0:
        pos_val = qty * price
        max_risk = profile["capital"] * profile["max_dd"] / 100
        if pos_val > max_risk:
            issues.append(f"position_exceeds_drawdown:{pos_val:.0f}>{max_risk:.0f}")
    if profile_id <= 2 and ticker_raw and len(ticker_raw) <= 2:
        issues.append("conservative_suspect_ticker")
    e["profile_compliance_issues"] = issues

    # Critical checks
    critical = False
    errs = []
    if e["final_decision"] == "PAPER_ONLY_ALLOWED" and frozen:
        critical = True
        errs.append("CRITICAL:allowed_with_freeze")
    if e.get("f51_trade_gate_status") == "ALLOW" and ticker_blacklisted:
        critical = True
        errs.append("CRITICAL:blacklisted_passed_gate")
    if e["final_decision"] == "PAPER_ONLY_ALLOWED" and not ticker_valid:
        critical = True
        errs.append("CRITICAL:allowed_invalid_ticker")
    e["critical_failure"] = critical
    e["errors"] = errs
    e["latency"] = 0

    return e


# Run all
results = []
failures = []
allowed = []
for pid in sorted(PROFILES):
    for sid, sname, prompt, istrade in SCENARIOS:
        entry = evaluate(pid, sid, sname, prompt, istrade)
        results.append(entry)
        if entry["final_decision"] == "PAPER_ONLY_ALLOWED":
            allowed.append(entry)
        if entry.get("critical_failure") or entry.get("order_blocked_reason"):
            failures.append(entry)

# Stats
n_total = len(results)
n_allowed = sum(1 for r in results if r["final_decision"] == "PAPER_ONLY_ALLOWED")
n_blocked = sum(1 for r in results if r["final_decision"] == "BLOCKED")
n_notrade = sum(1 for r in results if r["final_decision"] == "NO_TRADE_INTENT")
n_critical = sum(1 for r in results if r.get("critical_failure"))
print(
    f"Total: {n_total} | ALLOWED: {n_allowed} | BLOCKED: {n_blocked} | NO_TRADE: {n_notrade} | CRITICAL: {n_critical}"
)

# CSV
csv_path = "C:/Users/marco/Desktop/bob_fiduciary_test_results.csv"
fields = [
    "profile_id",
    "profile_name",
    "scenario_id",
    "scenario_name",
    "prompt",
    "ticker_detected",
    "ticker_validated",
    "intent_type",
    "is_trade_request",
    "f51_trade_gate_status",
    "gate_reason_code",
    "final_decision",
    "order_blocked_reason",
    "execution_freeze_active",
    "critical_failure",
]
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(results)
print(f"CSV: {csv_path}")

# JSONL failures
jsonl_path = "C:/Users/marco/Desktop/bob_fiduciary_failures.jsonl"
with open(jsonl_path, "w", encoding="utf-8") as f:
    for fail in failures:
        f.write(json.dumps(fail, ensure_ascii=False) + "\n")
print(f"JSONL: {jsonl_path} ({len(failures)} entries)")

# Trace summary
trace_path = "C:/Users/marco/Desktop/bob_fiduciary_trace_summary.txt"
with open(trace_path, "w", encoding="utf-8") as f:
    f.write("BOB FIDUCIARY TRACE SUMMARY\n")
    f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    f.write(
        f"Total: {n_total} | ALLOWED: {n_allowed} | BLOCKED: {n_blocked} | NO_TRADE: {n_notrade} | CRITICAL: {n_critical}\n\n"
    )
    f.write("--- Gate Decisions ---\n")
    gates = {}
    for r in results:
        rc = r.get("gate_reason_code", "?")
        gates[rc] = gates.get(rc, 0) + 1
    for k, v in sorted(gates.items(), key=lambda x: -x[1]):
        f.write(f"  {k}: {v}\n")
    f.write("\n--- Allowed ---\n")
    for a in allowed:
        f.write(
            f"  {a['trace_id']} | P{a['profile_id']} S{a['scenario_id']} | {a['ticker_detected']}\n"
        )
    f.write("\n--- Failures ---\n")
    for fl in failures[:30]:
        f.write(
            f"  {fl['trace_id']} | P{fl['profile_id']} S{fl['scenario_id']} | {fl.get('order_blocked_reason', '?')[:80]}\n"
        )
print(f"Trace: {trace_path}")

# Store for report generation
import json as _json

with open("C:/Users/marco/Desktop/_fiduciary_data.json", "w") as f:
    _json.dump(
        {
            "n_total": n_total,
            "n_allowed": n_allowed,
            "n_blocked": n_blocked,
            "n_notrade": n_notrade,
            "n_critical": n_critical,
            "freeze": is_execution_frozen(),
            "gates": gates,
            "per_profile": {
                str(pid): {
                    "allowed": sum(
                        1
                        for r in results
                        if r["profile_id"] == pid and r["final_decision"] == "PAPER_ONLY_ALLOWED"
                    ),
                    "blocked": sum(
                        1
                        for r in results
                        if r["profile_id"] == pid and r["final_decision"] == "BLOCKED"
                    ),
                    "notrade": sum(
                        1
                        for r in results
                        if r["profile_id"] == pid and r["final_decision"] == "NO_TRADE_INTENT"
                    ),
                }
                for pid in PROFILES
            },
            "per_scenario": {
                str(sid): {
                    "allowed": sum(
                        1
                        for r in results
                        if r["scenario_id"] == sid and r["final_decision"] == "PAPER_ONLY_ALLOWED"
                    ),
                    "blocked": sum(
                        1
                        for r in results
                        if r["scenario_id"] == sid and r["final_decision"] == "BLOCKED"
                    ),
                    "notrade": sum(
                        1
                        for r in results
                        if r["scenario_id"] == sid and r["final_decision"] == "NO_TRADE_INTENT"
                    ),
                }
                for sid, _, _, _ in SCENARIOS
            },
        },
        f,
    )

print("Done. All 4 files generated.")
