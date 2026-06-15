#!/usr/bin/env python
"""Executa o ciclo de aprendizado do FeedbackLoop.

Uso:
    python scripts/run_learning_cycle.py [--stats]

Flags:
    --stats: Mostra apenas estatísticas, sem executar ciclo completo
"""
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
src_root = project_root / "src"
sys.path.insert(0, str(src_root))
sys.path.insert(0, str(project_root))

try:
    from core.trading.feedback_loop import get_feedback_loop

    parser = argparse.ArgumentParser(description="Learning cycle do SuperEzio")
    parser.add_argument("--stats", action="store_true", help="Mostra apenas estatísticas")
    args = parser.parse_args()

    fb_loop = get_feedback_loop()

    if args.stats:
        stats = fb_loop.get_stats()
        print("\n=== ESTATÍSTICAS DE APRENDIZADO ===")
        print(f"Total de trades: {stats['total_trades']}")
        print(f"Trades fechados: {stats['closed_trades']}")
        print(f"Wins: {stats['wins']}")
        print(f"Losses: {stats['losses']}")
        print(f"Win rate: {stats['win_rate']*100:.1f}%")
        bias = stats.get("bias_report", {})
        if bias:
            print(f"Bias: {bias.get('bias')} ({bias.get('status')})")
        print(f"Lições registradas: {stats['lessons_logged']}")
        if stats.get('last_learning_cycle'):
            print(f"Último ciclo: {stats['last_learning_cycle']}")
        print("====================================\n")
    else:
        print("\n=== EXECUTANDO CICLO DE APRENDIZADO ===\n")
        results = fb_loop.run_learning_cycle()

        print(f"\nTimestamp: {results['timestamp']}")
        print(f"Teses fechadas C6: {results['theses_closed']}")
        print(f"Padrões encontrados: {results['patterns_found']}")
        print(f"Lições extraídas: {results['lessons_extracted']}")

        bias = results.get("bias_report", {})
        if bias:
            print(f"Bias detectado: {bias.get('bias')} ({bias.get('status')})")

        if results.get("bob_context"):
            print("\n=== CONTEXTO PARA BOB ===")
            print(results["bob_context"])
            print("=== FIM DO CONTEXTO ===\n")

        # Mostra estatísticas atualizadas
        stats = fb_loop.get_stats()
        print("\n=== ESTATÍSTICAS ATUALIZADAS ===")
        print(f"Win rate: {stats['win_rate']*100:.1f}%")
        print(f"Lições registradas: {stats['lessons_logged']}")
        print("====================================\n")

except ImportError as e:
    print(f"Erro ao importar: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Erro: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
