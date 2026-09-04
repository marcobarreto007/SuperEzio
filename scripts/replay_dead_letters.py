"""Replay manual da dead letter queue de ordens paper.

Consumidor da DLQ de journal (src/core/idempotency): re-persiste no journal —
NUNCA re-envia ordem ao broker ou ao pipeline — as entradas ``pending``,
uma a uma. Idempotente: trade ja persistido e entrada ja marcada
done/failed nao rodam de novo.

Uso:
    python scripts/replay_dead_letters.py             # replay de todas as pending
    python scripts/replay_dead_letters.py --dry-run   # so lista o que faria

Diretorio real: SUPEREZIO_DEAD_LETTER_DIR (default: <repo>/journal/dead_letter).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.idempotency import list_dead_letters
from core.pipeline.nodes.auto_execute_paper import replay_dead_letter_entry


def _line(entry: dict) -> str:
    reason = entry.get("failure_reason") or "?"
    return (
        f"{entry['ticker']} {entry['action']} qty={entry['qty']} "
        f"@ {entry['limit_price']} ({reason}) -> {entry['file']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="lista as pendentes sem executar replay",
    )
    args = parser.parse_args()

    pending = list_dead_letters()
    if not pending:
        print("DLQ vazia: nenhuma entrada pending em journal/dead_letter.")
        return 0
    print(f"DLQ: {len(pending)} pendente(s)")
    if args.dry_run:
        for entry in pending:
            print(f"  [dry-run] {_line(entry)}")
        return 0

    failures = 0
    for entry in pending:
        result = replay_dead_letter_entry(entry)
        outcome = result.get("reason") or result.get("trade_id") or result.get("error") or "?"
        print(f"  [{result['status']}] {entry['ticker']} {entry['action']} -> {outcome}")
        if result["status"] == "failed":
            failures += 1
    print(f"Replay concluido: {len(pending) - failures} ok, {failures} falhou.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
