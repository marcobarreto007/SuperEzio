#!/usr/bin/env python
"""Script para testar o sistema de aprendizado com trades simulados.

Cria trades paper de teste para validar:
1. PatternAnalyzer - identificação de padrões
2. LessonExtractor - extração de lições
3. LearningLog - registro de lições
4. FeedbackLoop - ciclo completo
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
src_root = project_root / "src"
sys.path.insert(0, str(src_root))
sys.path.insert(0, str(project_root))

from core.trading.paper_journal import PaperJournal, PaperTrade  # noqa: E402


def create_test_trades():
    """Cria trades de teste para various cenários."""
    journal = PaperJournal()

    # Trade 1: Win em momentum
    trade1 = PaperTrade(
        trade_id="test_momentum_win_001",
        ticker="AEHR",
        thesis="Momentum breakout com volume alto confirmado",
        direction="long",
        entry_date=(datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        entry_price=2.50,
        shares=100,
        entry_reasoning="Breakout confirmado com volume 3x média",
        verdict_at_entry="BUY",
        risk_assessment="alta - pennystock especulativa",
        expected_holding_period="swing",
        exit_date=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        exit_price=3.20,
        exit_reason="take_profit",
        outcome="win",
        thesis_correct=True,
        what_went_right="Breakout confirmado, volume sustentou",
        what_went_wrong="",
        lesson_learned="Momentum com volume confirmado funciona bem em pennystocks"
    )
    journal.open_trade(trade1)

    # Trade 2: Loss em thesis incorreta
    trade2 = PaperTrade(
        trade_id="test_thesis_loss_001",
        ticker="SNDL",
        thesis="Recuperação baseada em rumors de aquisição não verificado",
        direction="long",
        entry_date=(datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
        entry_price=4.00,
        shares=50,
        entry_reasoning="Rumor de aquisition sem fonte verificada",
        verdict_at_entry="WAIT",
        risk_assessment="alta - speculation",
        expected_holding_period="day_trade",
        exit_date=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        exit_price=3.50,
        exit_reason="stop_loss",
        outcome="loss",
        thesis_correct=False,
        what_went_right="",
        what_went_wrong="Tese baseada em rumor não verificado, catalyst não existiu",
        lesson_learned="Nunca entrar baseado em rumor não verificado, só filing/earnings confirmado"
    )
    journal.open_trade(trade2)

    # Trade 3: Win em earnings catalyst
    trade3 = PaperTrade(
        trade_id="test_earnings_win_001",
        ticker="PLUG",
        thesis="Earnings beat com guidance上调 elevada",
        direction="long",
        entry_date=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        entry_price=1.80,
        shares=150,
        entry_reasoning="Earnings pré-release mostrou beat forte",
        verdict_at_entry="BUY",
        risk_assessment="moderada",
        expected_holding_period="swing",
        exit_date=(datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(),
        exit_price=2.30,
        exit_reason="take_profit",
        outcome="win",
        thesis_correct=True,
        what_went_right="Earnings confirmaram tese, guidance forte",
        what_went_wrong="",
        lesson_learned="Earnings beat com guidance上调 elevada é catalyst confiável"
    )
    journal.open_trade(trade3)

    # Trade 4: Loss em risk management falha
    trade4 = PaperTrade(
        trade_id="test_risk_loss_001",
        ticker="GNUS",
        thesis="Recuperação técnica após oversell",
        direction="long",
        entry_date=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        entry_price=1.20,
        shares=200,
        entry_reasoning="RSI oversold, expectativa de bounce",
        verdict_at_entry="BUY",
        risk_assessment="alta - position size muito grande",
        expected_holding_period="day_trade",
        exit_date=(datetime.now(timezone.utc) - timedelta(hours=6)).isoformat(),
        exit_price=0.95,
        exit_reason="stop_loss",
        outcome="loss",
        thesis_correct=False,
        what_went_right="",
        what_went_wrong="Position size muito grande, stop muito largo, risco mal gerenciado",
        lesson_learned="Em pennystocks illíquid, position size deve ser menor e stop mais justo"
    )
    journal.open_trade(trade4)

    print("✓ Criados 4 trades de teste:")
    print("  - AEHR (win): momentum breakout")
    print("  - SNDL (loss): rumor não verificado")
    print("  - PLUG (win): earnings catalyst")
    print("  - GNUS (loss): risk management falha")


def main():
    print("\n=== TESTE DO SISTEMA DE APRENDIZADO ===\n")

    # 1. Criar trades de teste
    print("1. Criando trades de teste...")
    create_test_trades()

    # 2. Executar ciclo de aprendizado
    print("\n2. Executando ciclo de aprendizado...")
    try:
        from core.trading.feedback_loop import get_feedback_loop
        fb_loop = get_feedback_loop()
        results = fb_loop.run_learning_cycle()

        print("\nResultados:")
        print(f"  Timestamp: {results['timestamp']}")
        print(f"  Padrões encontrados: {results['patterns_found']}")
        print(f"  Lições extraídas: {results['lessons_extracted']}")

        if results.get("patterns"):
            print("\n  Padrões identificados:")
            for p in results["patterns"][:3]:
                print(f"    - {p['description']} (win rate: {p['win_rate']*100:.0f}%)")

        if results.get("lessons"):
            print("\n  Lições extraídas:")
            for lesson in results["lessons"][:3]:
                print(f"    - {lesson['title']}")

        # 3. Verificar stats
        stats = fb_loop.get_stats()
        print("\n3. Estatísticas do sistema:")
        print(f"  Total de trades: {stats['total_trades']}")
        print(f"  Trades fechados: {stats['closed_trades']}")
        print(f"  Win rate: {stats['win_rate']*100:.1f}%")
        print(f"  Lições registradas: {stats['lessons_logged']}")

        # 4. Renderizar contexto para Bob
        print("\n4. Contexto para Bob:")
        bob_context = fb_loop.render_for_bob()
        print(bob_context)

    except Exception as e:
        print(f"Erro: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n=== TESTE CONCLUÍDO ===\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
