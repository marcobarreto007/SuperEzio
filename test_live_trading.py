"""Teste Live Trading - Bob operando com dados reais.

Modo 1: Yahoo Finance (dados reais, paper execution local)
Modo 2: IBKR Paper (dados reais + execução real no TWS paper)

Requerimentos:
- yfinance: pip install yfinance
- IBKR: TWS Paper Trading aberto na porta 7497
"""

import os
import sys
import time
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

print("=" * 70)
print("BOB LIVE TRADING TEST")
print("=" * 70)

# Configurar modo
MODE = "YAHOO"  # ou "IBKR"
if len(sys.argv) > 1:
    MODE = sys.argv[1].upper()

print(f"\nModo: {MODE}")
print("-" * 70)

if MODE == "IBKR":
    print("\n⚠️  IBKR PAPER TRADING")
    print("1. Abra o TWS Paper Trading")
    print("2. Configure API → Aceitar conexões na porta 7497")
    print("3. Pressione ENTER quando pronto...")
    input()

# Importar e configurar
print("\nInicializando Bob...")

from core.trading.trading_engine_live import get_live_trading_engine

engine = get_live_trading_engine(
    use_ibkr=(MODE == "IBKR"),
    equity=10000.0,
)

print(f"✓ Engine criado | Equity: ${engine.equity:.2f}")

# Atualizar equity do IBKR se conectado
if MODE == "IBKR":
    print("\nConectando ao IBKR...")
    equity = engine.update_equity_from_broker()
    print(f"✓ IBKR Equity: ${equity:.2f}")

# Testar market data
print("\nTestando market data...")
if engine._market_data_provider:
    # Teste com AAPL
    data = engine._market_data_provider.get_data("AAPL")
    if data:
        print(f"✓ AAPL: ${data.last_price:.2f} ({data.change_pct:+.2f}%)")
        print(f"  Volume: {data.volume:,} | Bid: ${data.bid:.2f} | Ask: ${data.ask:.2f}")
    else:
        print("✗ Falhou ao obter dados da AAPL")

# Checar estado do mercado
from core.trading.market_hours import get_market_state
market = get_market_state(cached=False)
print(f"\nEstado do mercado: {market['phase']}")
print(f"Aberto: {market['is_open']}")

if not market['is_open']:
    print("\n⚠️  Mercado fechado. Scan funcionará mas não executará trades.")

# Configurar engine para ser agressivo (só para teste)
from core.trading.auto_executor import ExecutorConfig
from core.trading.risk_guard import RiskLimits

config = ExecutorConfig(
    daily_loss_limit=500,
    max_drawdown_pct=0.15,
    max_consecutive_losses=10,
    max_position_pct=0.20,
    max_total_exposure_pct=0.50,
    max_trades_per_day=20,
    enable_committee=False,  # Desabilitar committee para teste
    require_human_approval=False,
)
engine._executor.config = config

limits = RiskLimits(
    max_position_pct=0.20,
    max_notional_per_trade=5000,
    max_total_exposure_pct=0.50,
    max_same_asset_exposure_pct=0.30,
    min_avg_daily_volume=100000,
    max_trades_per_day=20,
)
engine._risk_guard.limits = limits

print(f"✓ Config agressiva definida")

print("\n" + "=" * 70)
print("MODO TRADING - Bob está vivo")
print("=" * 70)
print("\nComandos:")
print("  scan  - Scanear mercado")
print("  cycle  - Executar um ciclo completo")
print("  status  - Ver status")
print("  exit  - Sair")

# Loop interativo
while True:
    try:
        cmd = input("\nBob> ").strip().lower()

        if cmd == "exit":
            print("\nBob desligando. Até logo!")
            break

        elif cmd == "scan":
            print("\nScaneando mercado...")
            opportunities = engine.scan_market_real()

            print(f"\nEncontradas: {len(opportunities)} oportunidades")
            for opp in opportunities:
                print(f"\n  {opp.symbol}:")
                print(f"  - Sentimento: {opp.sentiment.value}")
                print(f"  - Preço: ${opp.entry_price:.2f}")
                print(f"  - Confiança: {opp.confidence:.0%}")
                print(f"  - SL: ${opp.stop_loss:.2f} | TP: ${opp.take_profit:.2f}")
                print(f"  - Thesis: {opp.thesis}")

        elif cmd == "cycle":
            print("\nExecutando ciclo completo...")
            summary = engine.run_one_cycle_real()

            print(f"\nResumo:")
            print(f"  - Mercado aberto: {summary['market_open']}")
            print(f"  - Oportunidades: {summary['opportunities']}")
            print(f"  - Trades executados: {summary['trades']}")
            print(f"  - Posições fechadas: {summary['closed']}")
            print(f"  - Equity: ${summary['equity']:.2f}")

        elif cmd == "status":
            status = engine.get_status_real()

            print(f"\n=== STATUS ===")
            print(f"Equity: ${status['engine']['equity']:.2f}")
            print(f"Trades totais: {status['engine']['total_trades']}")
            print(f"Wins: {status['engine']['total_wins']}")
            print(f"Losses: {status['engine']['total_losses']}")
            print(f"Win rate: {status['engine']['win_rate']:.1%}")
            print(f"Total PnL: ${status['engine']['total_pnl']:.2f}")
            print(f"XP: {status['engine']['xp_level']}")
            print(f"\nPosições abertas: {status['positions']['open']}")
            print(f"Valor total: ${status['positions']['total_value']:.2f}")
            print(f"PnL unrealizado: ${status['positions']['unrealized_pnl']:.2f}")
            print(f"\nLive mode: {status['live']}")
            print(f"Market data: {status['market_data']}")

        elif cmd == "auto":
            print("\n⚠️  Modo AUTO - Bob vai operar sozinho")
            print("Pressione CTRL+C para parar")

            cycles = 0
            try:
                while True:
                    summary = engine.run_one_cycle_real()
                    cycles += 1

                    if cycles % 5 == 0:
                        print(f"\nCiclo {cycles}: {summary['trades']} trades, ${summary['equity']:.2f} equity")

                    time.sleep(30)  # Esperar 30s entre ciclos

            except KeyboardInterrupt:
                print("\n\nAuto mode interrompido.")

        elif cmd == "help":
            print("\nComandos disponíveis:")
            print("  scan   - Scanear mercado por oportunidades")
            print("  cycle  - Executar um ciclo completo")
            print("  status - Ver status completo")
            print("  auto   - Modo automático (Bob sozinho)")
            print("  exit   - Sair")

        else:
            print(f"\nComando desconhecido: {cmd}")
            print("Digite 'help' para ver comandos.")

    except KeyboardInterrupt:
        print("\n\nBob desligando. Até logo!")
        break
    except Exception as e:
        print(f"\nErro: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 70)
print("BOB LIVE TRADING - FIM")
print("=" * 70)
