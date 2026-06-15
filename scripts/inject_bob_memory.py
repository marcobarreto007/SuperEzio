#!/usr/bin/env python
"""Injeta conhecimento direto na memória do Bob."""
import json
from pathlib import Path
from datetime import datetime, timezone

# Carregar knowledge construído
memory_file = Path("output/bob_memory_small_caps.json")
if not memory_file.exists():
    print("Run build_bob_memory.py first")
    exit(1)

with open(memory_file) as f:
    knowledge = json.load(f)

# Converter para formato conversation_memory.jsonl
def create_turn(ticker: str, knowledge: dict) -> dict:
    """Cria uma ConversationTurn formatada."""
    name = knowledge["name"]
    thesis = knowledge["thesis"]
    risks = ", ".join(knowledge["risks"])
    verdict = knowledge["verdict"]
    conf = knowledge["confidence"]

    user_msg = f"What do you know about {ticker} ({name})? Risks, thesis, verdict?"
    bob_response = f"""{ticker} ({name}) Analysis:

THESIS: {thesis}

RISKS: {risks}

SECTOR: {knowledge["sector"]} | MARKET CAP: {knowledge["market_cap"]}

CATALYSTS: {", ".join(knowledge["catalysts"])}

VERDICT: {verdict} (confidence: {int(conf*100)}%)

NOTE: This is a nano/micro cap with high risk. Dilution, delisting, and binary event risk are elevated. Position sizing should be 1-2% maximum per ticker. This is not investment advice.

Source: F51 Small Caps Research 2026-06-15"""

    return {
        "session_id": "small_caps_memory_injection",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_message": user_msg,
        "bob_response": bob_response,
        "context_summary": f"F51 Small Caps Research: {ticker} = {verdict}",
        "embedding_vector": [0.0] * 128,  # Placeholder
        "ticker_discussed": ticker,
        "thesis_formed": thesis,
        "verdict": verdict,
        "confidence": conf,
        "tags": ["small_cap", "research", knowledge["sector"]],
        "category": "ticker_analysis"
    }

# Gerar turns para cada small cap
turns = []
for cap in knowledge["small_caps"]:
    turns.append(create_turn(cap["ticker"], cap))

# Adicionar risk patterns como turn conceituais
risk_msg = "What are the top risks when investing in nano caps under $50M?"
risk_response = "TOP NANO CAP RISKS:\n\n" + "\n".join(f"{i+1}. {p}" for i, p in enumerate(knowledge["risk_patterns"]))

turns.append({
    "session_id": "small_caps_memory_injection",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "user_message": risk_msg,
    "bob_response": risk_response,
    "context_summary": "F51 Small Caps Research: Risk patterns for nano caps",
    "embedding_vector": [0.0] * 128,
    "ticker_discussed": "",
    "thesis_formed": "",
    "verdict": "AVOID_POSITION_SIZING",
    "confidence": 0.8,
    "tags": ["small_cap", "risk", "education"],
    "category": "general"
})

# Injetar na memória conversacional
conversation_memory = Path("data/conversation_memory.jsonl")

# Backup primeiro
backup = conversation_memory.with_suffix(".jsonl.backup")
if conversation_memory.exists():
    import shutil
    shutil.copy(conversation_memory, backup)
    print(f"Backed up to {backup}")

# Adicionar novos turns
with open(conversation_memory, "a") as f:
    for turn in turns:
        f.write(json.dumps(turn) + "\n")

print(f"\nInjected {len(turns)} turns into Bob's memory:")
print(f"  - {len(knowledge['small_caps'])} small caps")
print(f"  - 1 risk patterns summary")
print(f"\nBob now 'knows' these small caps without slow CEO inference.")
print(f"\nNext time Bob analyzes these tickers, he'll have context from memory.")
