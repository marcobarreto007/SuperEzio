#!/usr/bin/env python
"""Encher a cabeça do Bob com conhecimento estruturado."""
import json
from pathlib import Path
from datetime import datetime, timezone

# 15 small caps — knowledge estruturado
SMALL_CAPS_KNOWLEDGE = [
    {
        "ticker": "AEHR",
        "name": "Aehr Test Systems",
        "sector": "Semiconductors",
        "market_cap": "<$300M",
        "thesis": "Semiconductor testing equipment for AI/quantum chips. Bull: AI boom needs testing. Bear: Cyclical, customer concentration.",
        "risks": ["Customer concentration", "Cyclicality", "Competition"],
        "catalysts": ["AI chip demand", "Quantum computing testing"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.6
    },
    {
        "ticker": "PLAB",
        "name": "Photronics",
        "sector": "Semiconductors",
        "market_cap": "<$500M",
        "thesis": "Photomasks for AI/quantum. Bull: Essential for chip manufacturing. Bear: Capex heavy, low margin.",
        "risks": ["Capex intensity", "Low margins", "Tech cycles"],
        "catalysts": ["AI photomask demand", "Quantum mask complexity"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.55
    },
    {
        "ticker": "SKYT",
        "name": "SkyWater Technology",
        "sector": "Semiconductors",
        "market_cap": "<$200M",
        "thesis": "Specialized semiconductor manufacturing. Bull: Niche manufacturing. Bear: Low volume, high fixed cost.",
        "risks": ["Low volume", "High fixed cost", "Competition"],
        "catalysts": ["Specialized process demand", "US manufacturing push"],
        "verdict": "HIGH_RISK",
        "confidence": 0.5
    },
    {
        "ticker": "INOD",
        "name": "Innodata",
        "sector": "AI/ESG",
        "market_cap": "<$100M",
        "thesis": "AI data solutions for ESG/finance. Bull: ESG compliance demand. Bear: Small player, commoditization.",
        "risks": ["Commoditization", "Competition", "ESG regulatory risk"],
        "catalysts": ["ESG regulations", "AI data demand"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.55
    },
    {
        "ticker": "USIO",
        "name": "Univest",
        "sector": "Semiconductor IP",
        "market_cap": "<$50M",
        "thesis": "Semiconductor IP and solutions. Bull: IP licensing model. Bear: Tiny, execution risk.",
        "risks": ["Execution risk", "Tiny cap", "Liquidity"],
        "catalysts": ["IP licensing deals", "New designs"],
        "verdict": "HIGH_RISK",
        "confidence": 0.45
    },
    {
        "ticker": "SIGA",
        "name": "SIGA Technologies",
        "sector": "Biotech/Pharma",
        "market_cap": "~$200M",
        "thesis": "TPOXX antiviral for smallpox/monkeypox. Bull: Government stockpiles, outbreak fears. Bear: Binary event risk, low recurring revenue.",
        "risks": ["Binary event", "Low recurring revenue", "Government budget"],
        "catalysts": ["Outbreak news", "Government contracts", "FDA approvals"],
        "verdict": "CATALYST_PLAY",
        "confidence": 0.65
    },
    {
        "ticker": "NEPH",
        "name": "NephroSense",
        "sector": "Biotech/Diagnostics",
        "market_cap": "<$50M",
        "thesis": "Kidney disease diagnostic tech. Bull: Medical need, aging population. Bear: FDA approval risk, tiny cap.",
        "risks": ["FDA approval", "Tiny cap", "Adoption"],
        "catalysts": ["FDA milestones", "Clinical data", "Partnerships"],
        "verdict": "HIGH_RISK_BINARY",
        "confidence": 0.4
    },
    {
        "ticker": "PDSB",
        "name": "PDS Biotechnology",
        "sector": "Biotech/Immunotherapy",
        "market_cap": "<$50M",
        "thesis": "Cancer immunotherapy. Bull: Novel approach, oncology demand. Bear: Clinical trial risk, dilution.",
        "risks": ["Trial failure", "Dilution", "Competition"],
        "catalysts": ["Trial readouts", "Partnerships", "Data publications"],
        "verdict": "HIGH_RISK_BINARY",
        "confidence": 0.4
    },
    {
        "ticker": "IMRX",
        "name": "Immuneering",
        "sector": "Biotech/Oncology",
        "market_cap": "<$50M",
        "thesis": "Precision oncology platforms. Bull: Targeted therapies. Bear: Cash burn, tiny cap.",
        "risks": ["Cash burn", "Tiny cap", "Platform risk"],
        "catalysts": ["Clinical data", "Platform validation", "Partnerships"],
        "verdict": "HIGH_RISK_BINARY",
        "confidence": 0.35
    },
    {
        "ticker": "NUVB",
        "name": "Nuvation Bio",
        "sector": "Biotech/Oncology",
        "market_cap": "~$500M",
        "thesis": "Precision oncology therapies. Bull: Diversified pipeline. Bear: Execution risk, competitive landscape.",
        "risks": ["Execution", "Competition", "Clinical risk"],
        "catalysts": ["Trial results", "FDA approvals", "Acquisitions"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.55
    },
    {
        "ticker": "FINV",
        "name": "FinVolution",
        "sector": "Fintech/Lending",
        "market_cap": "<$200M",
        "thesis": "Fintech lending platform in China. Bull: Consumer credit demand. Bear: Regulatory risk, credit quality.",
        "risks": ["Chinese regulation", "Credit quality", "Competition"],
        "catalysts": ["User growth", "International expansion", "Rate changes"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.5
    },
    {
        "ticker": "III",
        "name": "Hamilton Insurance",
        "sector": "Insurance/Insurtech",
        "market_cap": "<$200M",
        "thesis": "Insurance technology. Bull: Underwriting discipline, tech advantage. Bear: Catastrophe risk, competition.",
        "risks": ["Catastrophe", "Competition", "Interest rates"],
        "catalysts": ["Underwriting results", "Tech adoption", "M&A"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.55
    },
    {
        "ticker": "LX",
        "name": "LexinFintech",
        "sector": "Fintech/Lending",
        "market_cap": "<$200M",
        "thesis": "Digital lending in China. Bull: Market demand, tech. Bear: Delinquency risk, regulation.",
        "risks": ["Delinquency", "Regulation", "Competition"],
        "catalysts": ["Delinquency trends", "User growth", "Regulatory clarity"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.5
    },
    {
        "ticker": "BNRG",
        "name": "Brenmiller Energy",
        "sector": "Energy/Storage",
        "market_cap": "~$3M (NANO)",
        "thesis": "Thermal energy storage. Bull: Energy storage demand. Bear: Reverse split 1:100 done, survival risk.",
        "risks": ["SURVIVAL", "Dilution", "Delisting", "Liquidity"],
        "catalysts": ["Contracts", "Partnerships", "Energy policy"],
        "verdict": "EXTREME_RISK_SURVIVAL",
        "confidence": 0.2
    },
    {
        "ticker": "DIBS",
        "name": "1stdibs",
        "sector": "E-commerce/Marketplace",
        "market_cap": "~$500M",
        "thesis": "Luxury marketplace. Bull: Niche luxury e-commerce. Bear: Growth decelerating, competition.",
        "risks": ["Growth slowdown", "Competition", "Luxury cyclicality"],
        "catalysts": ["Growth reacceleration", "International", "M&A"],
        "verdict": "SPECULATIVE_BUY",
        "confidence": 0.5
    },
]

# Patterns de risco para nano caps — o ladrão volta à cena
RISK_PATTERNS = [
    "Nano caps (<$50M) have high delisting risk",
    "Reverse splits often signal survival mode",
    "Biotech penny stocks are binary (trial success/failure)",
    "Low liquidity = wide bid-ask spreads, slippage",
    "Pump-and-dump: volume spikes without news are red flags",
    "Insider selling before news is common fraud pattern",
    "Dilution is the default funding path for nano caps",
    "Bankruptcy risk is real for cash-burning micro caps",
]

def main() -> None:
    """Build Bob's memory fast."""
    output = Path("output") / "bob_memory_small_caps.json"
    output.parent.mkdir(exist_ok=True)

    memory = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "small_caps": SMALL_CAPS_KNOWLEDGE,
        "risk_patterns": RISK_PATTERNS,
        "training_command": "Inject this into conversation_memory.jsonl or use as RAG context",
    }

    with open(output, "w") as f:
        json.dump(memory, f, indent=2)

    print(f"Bob memory built: {output}")
    print(f"  - {len(SMALL_CAPS_KNOWLEDGE)} small caps with thesis")
    print(f"  - {len(RISK_PATTERNS)} risk patterns")
    print(f"\nNext: Inject into Bob's context via RAG or conversation memory")

if __name__ == "__main__":
    main()
