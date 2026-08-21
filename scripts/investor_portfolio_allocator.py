"""Investor Portfolio & Capital Allocator CLI for SuperEzio.

Provides deterministic, institutional-grade personal financial allocation:
1. Calculates required emergency cash reserves based on monthly expense burn.
2. Evaluates high-interest debt payoff prioritization vs market hurdle rates.
3. Allocates surplus into Core & Explore ETF portfolios.
4. Matches allocation targets against the 108 TD Direct commission-free ETFs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
COMMISSION_FREE_MANIFEST = ROOT / "config" / "td_direct_commission_free_etfs.json"


@dataclass
class AllocationPlan:
    total_capital: float
    currency: str
    emergency_reserve: float
    emergency_months: float
    debt_payoff: float
    investable_surplus: float
    core_allocation: float
    explore_allocation: float
    recommended_etfs: List[Dict[str, Any]]
    account_routing: Dict[str, float]
    summary_verdict: str


def load_commission_free_etfs() -> List[str]:
    if not COMMISSION_FREE_MANIFEST.exists():
        return []
    try:
        with open(COMMISSION_FREE_MANIFEST, "r", encoding="utf-8") as f:
            data = json.load(f)
            symbols = data.get("symbols", {})
            can = symbols.get("CAN", [])
            us = symbols.get("US", [])
            return can + us
    except Exception:
        return []


def calculate_allocation(
    total_capital: float,
    monthly_expenses: float = 3500.0,
    emergency_months: float = 4.0,
    debt_balance: float = 0.0,
    debt_interest_rate: float = 0.0,
    risk_tolerance: str = "moderate",  # conservative | moderate | growth | aggressive
    currency: str = "CAD",
) -> AllocationPlan:
    if total_capital <= 0:
        raise ValueError("Total capital must be greater than zero")

    # 1. Emergency Cash Reserve
    needed_reserve = monthly_expenses * emergency_months
    emergency_reserve = min(total_capital, needed_reserve)
    remaining_capital = total_capital - emergency_reserve

    # 2. High-Interest Debt Payoff (if interest > 6.0% hurdle)
    debt_payoff = 0.0
    if debt_balance > 0 and debt_interest_rate >= 6.0:
        debt_payoff = min(remaining_capital, debt_balance)
        remaining_capital -= debt_payoff

    # 3. Investable Surplus
    investable_surplus = max(0.0, remaining_capital)

    # 4. Core vs Explore split
    explore_weight = {
        "conservative": 0.0,
        "moderate": 0.10,
        "growth": 0.15,
        "aggressive": 0.20,
    }.get(risk_tolerance.lower(), 0.10)

    explore_allocation = round(investable_surplus * explore_weight, 2)
    core_allocation = round(investable_surplus - explore_allocation, 2)

    # 5. ETF matching from verified 108 TD Direct commission-free universe
    valid_symbols = set(load_commission_free_etfs())
    recommended_etfs: List[Dict[str, Any]] = []

    if investable_surplus > 0:
        candidates: List[Dict[str, Any]] = []
        if risk_tolerance.lower() == "conservative":
            candidates = [
                {
                    "ticker": "VBAL.TO",
                    "base_symbol": "VBAL",
                    "name": "Vanguard Balanced ETF Portfolio (60/40)",
                    "weight_pct": 70.0,
                    "category": "balanced_core",
                },
                {
                    "ticker": "VAB.TO",
                    "base_symbol": "VAB",
                    "name": "Vanguard Canadian Aggregate Bond Index ETF",
                    "weight_pct": 30.0,
                    "category": "fixed_income_preservation",
                },
            ]
        elif risk_tolerance.lower() == "moderate":
            candidates = [
                {
                    "ticker": "VEQT.TO",
                    "base_symbol": "VEQT",
                    "name": "Vanguard All-Equity ETF Portfolio (100% Equity)",
                    "weight_pct": 50.0,
                    "category": "global_all_cap",
                },
                {
                    "ticker": "VFV.TO",
                    "base_symbol": "VFV",
                    "name": "Vanguard S&P 500 Index ETF",
                    "weight_pct": 30.0,
                    "category": "us_large_cap",
                },
                {
                    "ticker": "VCN.TO",
                    "base_symbol": "VCN",
                    "name": "Vanguard FTSE Canada All Cap Index ETF",
                    "weight_pct": 20.0,
                    "category": "canada_total_market",
                },
            ]
        else:
            candidates = [
                {
                    "ticker": "VFV.TO",
                    "base_symbol": "VFV",
                    "name": "Vanguard S&P 500 Index ETF",
                    "weight_pct": 45.0,
                    "category": "us_large_cap",
                },
                {
                    "ticker": "VCN.TO",
                    "base_symbol": "VCN",
                    "name": "Vanguard FTSE Canada All Cap Index ETF",
                    "weight_pct": 25.0,
                    "category": "canada_total_market",
                },
                {
                    "ticker": "VIU.TO",
                    "base_symbol": "VIU",
                    "name": "Vanguard FTSE Developed All Cap ex North America",
                    "weight_pct": 20.0,
                    "category": "international_developed",
                },
                {
                    "ticker": "MNG_TACTICAL",
                    "base_symbol": "TACTICAL",
                    "name": "Mangala / Tactical Swings (Stop 3%)",
                    "weight_pct": 10.0,
                    "category": "tactical_explore",
                    "allow_unverified": True,  # tactical bucket, not an ETF
                },
            ]

        for cand in candidates:
            base_sym = cand.get("base_symbol", "")
            is_cf = base_sym in valid_symbols
            if not is_cf and not cand.get("allow_unverified"):
                # Fail-closed recommendation: an ETF that is not in the 108
                # commission-free universe must not be suggested as a 0-fee pick.
                continue
            allocated_dollars = round(investable_surplus * (cand["weight_pct"] / 100.0), 2)
            recommended_etfs.append(
                {
                    "ticker": cand["ticker"],
                    "name": cand["name"],
                    "weight": f"{cand['weight_pct']:.0f}%",
                    "weight_pct": cand["weight_pct"],
                    "allocated_amount": allocated_dollars,
                    "commission_free_verified": is_cf,
                    "category": cand["category"],
                }
            )

    # 6. Account Routing (Canada TFSA / RRSP / Non-Registered)
    tfsa_room_estimate = 7000.0
    account_routing = {
        "tfsa_tax_free": min(investable_surplus, tfsa_room_estimate),
        "rrsp_or_fhsa": max(0.0, min(investable_surplus - tfsa_room_estimate, 10000.0)),
        "hisa_cash_reserve": emergency_reserve,
        "debt_cleared": debt_payoff,
    }

    verdict = (
        f"Alocacao Segura: {emergency_reserve:.2f} {currency} em Reserva ({emergency_months:.1f} meses), "
        f"{debt_payoff:.2f} {currency} em Dividas ({debt_interest_rate}% juros) e "
        f"{investable_surplus:.2f} {currency} em Ativos Produtivos Core/Explore."
    )

    return AllocationPlan(
        total_capital=total_capital,
        currency=currency,
        emergency_reserve=round(emergency_reserve, 2),
        emergency_months=emergency_months,
        debt_payoff=round(debt_payoff, 2),
        investable_surplus=round(investable_surplus, 2),
        core_allocation=core_allocation,
        explore_allocation=explore_allocation,
        recommended_etfs=recommended_etfs,
        account_routing=account_routing,
        summary_verdict=verdict,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="SuperEzio Investor Portfolio Allocator")
    parser.add_argument("--capital", type=float, default=25000.0, help="Total capital in CAD")
    parser.add_argument("--expenses", type=float, default=3500.0, help="Monthly expenses in CAD")
    parser.add_argument(
        "--emergency-months", type=float, default=4.0, help="Months of emergency buffer"
    )
    parser.add_argument(
        "--debt-balance", type=float, default=0.0, help="High interest debt balance"
    )
    parser.add_argument("--debt-rate", type=float, default=0.0, help="Debt interest rate in %")
    parser.add_argument(
        "--risk", choices=["conservative", "moderate", "growth", "aggressive"], default="moderate"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    plan = calculate_allocation(
        total_capital=args.capital,
        monthly_expenses=args.expenses,
        emergency_months=args.emergency_months,
        debt_balance=args.debt_balance,
        debt_interest_rate=args.debt_rate,
        risk_tolerance=args.risk,
    )

    if args.json:
        print(json.dumps(asdict(plan), indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 60)
        print("[SUPEREZIO INVESTOR ALLOCATION PLAN]")
        print("=" * 60)
        print(f"Capital Total:          CAD ${plan.total_capital:,.2f}")
        print(
            f"Reserva de Emergencia:  CAD ${plan.emergency_reserve:,.2f} ({plan.emergency_months:.1f} meses)"
        )
        print(f"Amortizacao de Dividas: CAD ${plan.debt_payoff:,.2f}")
        print(f"Excedente Investivel:   CAD ${plan.investable_surplus:,.2f}")
        print(f"  |-- Core (Longo Prazo): CAD ${plan.core_allocation:,.2f}")
        print(f"  \\-- Explore (Tatico):   CAD ${plan.explore_allocation:,.2f}")
        print("-" * 60)
        print("Roteamento de Contas Sugerido:")
        for acct, val in plan.account_routing.items():
            print(f"  * {acct:<20}: CAD ${val:,.2f}")
        print("ETFs Recomendados (TD Commission-Free Universe):")
        for etf in plan.recommended_etfs:
            cf_tag = "TD 0-Fee: YES" if etf.get("commission_free_verified") else "TD 0-Fee: N/A"
            amt = etf.get("allocated_amount", 0.0)
            print(
                f"  * [{etf['weight']:>4}] CAD ${amt:>8,.2f} | {etf['ticker']:<10} | [{cf_tag}] - {etf['name']}"
            )
        print("=" * 60)
        print(f"Veredito: {plan.summary_verdict}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
