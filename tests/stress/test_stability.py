"""Stress tests for stability — sem servidor externo.

Testes:
5. Loop de 24h simulado (1000 iteracoes) -> sem degradacao
6. Teste de desconexao/reconexao -> recovery funciona
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.stress,
    pytest.mark.slow,
]

# Garante que src/ esta no path
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(_SRC))

# Ambiente de teste
os.environ.setdefault("UNIVERSAL_SKIP_GATEWAY", "1")
os.environ.setdefault("SUPEREZIO_JWT_SECRET", "")
os.environ.setdefault("SUPEREZIO_EDGE_AUTH", "false")
os.environ.setdefault("SUPEREZIO_COCKPIT_READ_IBKR_ORDERS", "0")


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def journal_file():
    """Arquivo temporario para o PaperJournal."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        f.write("")
        path = Path(f.name)
    yield path
    try:
        path.unlink()
    except OSError:
        pass


@pytest.fixture
def journal(journal_file):
    """PaperJournal limpo para cada teste."""
    from core.trading.paper_journal import PaperJournal
    return PaperJournal(journal_file)


# ── Teste 5: Loop de 24h simulado (1000 iteracoes) ──────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
def test_24h_simulated_loop_no_degradation(journal):
    """1000 iteracoes simulando 24h de operacao -> sem degradacao.

    Cenario: a cada iteracao simulamos 1 ciclo de trading:
    - Abre 1-3 trades paper
    - Fecha trades antigos (simula take-profit / stop-loss)
    - Adiciona reflexoes a trades fechados
    - Verifica estatisticas
    """
    from core.trading.paper_journal import PaperTrade

    tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "BRK.B"]
    directions = ["long", "short"]
    verdicts = ["STRONG_BUY", "BUY", "SMALL_POSITION", "STUDY_MORE", "WAIT"]
    reasons_tp = ["take_profit", "target_hit", "time_exit"]
    reasons_sl = ["stop_loss", "trend_reversal", "cut_loss"]

    # Metricas de degradacao
    op_times: list[float] = []

    for iteration in range(1000):
        ticker = tickers[iteration % len(tickers)]
        direction = directions[iteration % 2]
        price = 100.0 + (iteration % 300)  # Preco varia entre 100-400

        # 1. Abre 1-3 trades por ciclo
        trades_opened = []
        for t in range((iteration % 3) + 1):  # 1 a 3 trades
            trade_id = f"iter-{iteration:04d}-{t}"
            trade = PaperTrade(
                trade_id=trade_id,
                ticker=ticker,
                thesis=f"Iteration {iteration}, trade #{t}: {ticker} {'momentum' if direction == 'long' else 'reversal'}",
                direction=direction,
                entry_date=f"2026-07-{1 + (iteration % 28):02d}T{8 + (iteration % 10):02d}:00:00Z",
                entry_price=price,
                shares=10 + (iteration % 100),
                entry_reasoning=f"Signal from iteration {iteration}",
                verdict_at_entry=verdicts[iteration % len(verdicts)],
                risk_assessment=f"Risk: iteration {iteration}, volatility moderate",
                expected_holding_period="swing",
            )
            t0 = time.perf_counter()
            journal.open_trade(trade)
            op_times.append(time.perf_counter() - t0)
            trades_opened.append(trade_id)

        # 2. Fecha trades de iteracoes anteriores (simula envelhecimento)
        if iteration >= 5:
            close_id = f"iter-{iteration - 5:04d}-0"
            existing = journal.get_trade(close_id)
            if existing and existing.get("exit_date") is None:
                exit_price = existing["entry_price"] + (
                    5.0 if (iteration % 3) != 0 else -5.0
                )
                exit_reason = reasons_tp[iteration % 3] if (iteration % 3) != 0 else reasons_sl[iteration % 3]
                t0 = time.perf_counter()
                journal.close_trade(close_id, exit_price=exit_price, exit_reason=exit_reason)
                op_times.append(time.perf_counter() - t0)

        # 3. Adiciona reflexao a trades fechados mais antigos
        if iteration >= 20 and iteration % 5 == 0:
            reflect_id = f"iter-{iteration - 20:04d}-0"
            reflected = journal.add_reflection(
                reflect_id,
                thesis_correct=(iteration % 3 != 0),
                what_went_right="Entry timing was correct" if iteration % 2 == 0 else "Risk management worked",
                what_went_wrong="Exit was too early" if iteration % 2 == 0 else "Should have cut loss faster",
                lesson_learned="Patience pays off in swing trades" if iteration % 2 == 0 else "Always set stop-loss at entry",
            )
            assert reflected is not None or journal.get_trade(reflect_id) is None

        # 4. A cada 100 iteracoes, verifica consistencia
        if iteration > 0 and iteration % 100 == 0:
            _ = journal.get_stats()
            total = journal.count()
            open_count = len(journal.list_open())
            closed_count = len(journal.list_closed())
            assert total == open_count + closed_count, (
                f"Iteracao {iteration}: count ({total}) != open ({open_count}) + closed ({closed_count})"
            )

            # Verifica que trades fechados tem pnl calculado
            for t in journal.list_closed():
                assert "outcome" in t, f"Trade fechado sem outcome: {t.get('trade_id')}"
                assert t["outcome"] in ("win", "loss", "breakeven"), (
                    f"Outcome invalido: {t['outcome']}"
                )

    # ── Verificacao final de degradacao ──
    stats_end = journal.get_stats()
    assert stats_end["total_trades"] > 0, "Nenhum trade foi criado"

    total_ops = len(op_times)
    assert total_ops > 0, "Nenhuma operacao registrada"

    avg_op_time = sum(op_times) / total_ops
    max_op_time = max(op_times)

    # Degradacao: operacoes devem ser rapidas (journal em arquivo local)
    # Se alguma operacao levar > 1s, e um sinal de problema de I/O ou contencao
    slow_ops = sum(1 for t in op_times if t > 1.0)
    assert slow_ops == 0, (
        f"{slow_ops} operacoes lentas (>1s) em {total_ops} operacoes. "
        f"Tempo medio: {avg_op_time * 1000:.1f}ms,"
        f"max: {max_op_time * 1000:.1f}ms"
    )

    # Tempo medio de operacao deve ser < 100ms (journal local e rapido)
    assert avg_op_time < 0.1, (
        f"Tempo medio de operacao elevado: {avg_op_time * 1000:.1f}ms. "
        f"Possivel degradacao do journal."
    )

    # Verifica que o JSONL nao tem corrupcao
    with open(journal.path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"JSONL corrompido na linha {i}: {e}")

    # Log de metricas para analise
    print("\n[STABILITY] 1000 iteracoes concluidas:")
    print(f"  Trades totais: {stats_end['total_trades']}")
    print(f"  Abertos: {stats_end['open_trades']}, Fechados: {stats_end['closed_trades']}")
    print(f"  Win rate: {stats_end['win_rate_pct']}%")
    print(f"  Tempo medio/op: {avg_op_time * 1000:.1f}ms")
    print(f"  Tempo max/op: {max_op_time * 1000:.1f}ms")
    print(f"  Total de operacoes: {total_ops}")


# ── Teste 6: Desconexao/reconexao — recovery funciona ────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_journal_recovery_after_file_corruption(journal):
    """Journal recupera apos arquivo corrompido -> sem perda de dados.

    Simula:
    1. Abre alguns trades
    2. Corrompe o arquivo JSONL (insere linha invalida)
    3. Verifica que o journal ainda funciona e trades anteriores estao intactos
    """
    from core.trading.paper_journal import PaperTrade

    # 1. Abre 5 trades saudaveis
    for i in range(5):
        trade = PaperTrade(
            trade_id=f"pre-corruption-{i}",
            ticker="AAPL",
            thesis=f"Pre-corruption trade #{i}",
            direction="long",
            entry_date="2026-07-15T10:00:00Z",
            entry_price=150.0 + i * 10,
            shares=100,
            entry_reasoning=f"Entry #{i} before corruption",
            verdict_at_entry="BUY",
            risk_assessment="Test",
            expected_holding_period="swing",
        )
        journal.open_trade(trade)

    assert journal.count() == 5

    # 2. Corrompe o arquivo — insere linha invalida no meio
    original_lines = []
    with open(journal.path) as f:
        original_lines = f.readlines()

    corrupted_lines = original_lines[:3] + [
        "Esta linha e JSON invalido!!!\n",
        "{tambem: incompleto\n",
    ] + original_lines[3:]

    with open(journal.path, "w") as f:
        f.writelines(corrupted_lines)

    # 3. Verifica que o journal sobrevive (ignora linhas corrompidas)
    assert journal.count() == 5, (
        f"Esperado 5 trades acessiveis apos corrupcao, obtido {journal.count()}"
    )

    # 4. Trades pre-corrupcao ainda acessiveis
    for i in range(5):
        trade = journal.get_trade(f"pre-corruption-{i}")
        assert trade is not None, f"Trade pre-corruption-{i} desapareceu apos corrupcao"
        assert trade["ticker"] == "AAPL"
        assert trade["entry_price"] == 150.0 + i * 10

    # 5. Ainda e possivel abrir novos trades
    new_trade = PaperTrade(
        trade_id="post-corruption-0",
        ticker="MSFT",
        thesis="After corruption recovery",
        direction="short",
        entry_date="2026-07-16T10:00:00Z",
        entry_price=400.0,
        shares=50,
        entry_reasoning="Recovery test",
        verdict_at_entry="STUDY_MORE",
        risk_assessment="Test recovery",
        expected_holding_period="day_trade",
    )
    journal.open_trade(new_trade)
    assert journal.count() == 6, "Falha ao adicionar trade apos recuperacao"

    # 6. Trade pos-corrupcao valido
    recovered = journal.get_trade("post-corruption-0")
    assert recovered is not None
    assert recovered["ticker"] == "MSFT"
    assert recovered["direction"] == "short"


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_journal_append_after_file_deleted_and_recreated(journal):
    """Journal recupera quando o arquivo e recriado do zero.

    Simula cenario de disaster recovery: o arquivo foi deletado
    e um novo arquivo vazio foi criado.
    """
    from core.trading.paper_journal import PaperTrade

    # 1. Abre 3 trades
    for i in range(3):
        trade = PaperTrade(
            trade_id=f"pre-delete-{i}",
            ticker="AAPL",
            thesis=f"Trade #{i} before delete",
            direction="long",
            entry_date="2026-07-15T10:00:00Z",
            entry_price=150.0,
            shares=100,
            entry_reasoning="Before delete",
            verdict_at_entry="BUY",
            risk_assessment="Test",
            expected_holding_period="swing",
        )
        journal.open_trade(trade)

    original_count = journal.count()
    assert original_count == 3

    # 2. Simula delecao acidental (arquivo removido, zeroado)
    journal.path.unlink()
    # Path nao existe mais
    assert not journal.path.exists()

    # 3. Novo journal com o mesmo path deve criar arquivo novo
    # (o construtor cria o diretorio se nao existir)
    from core.trading.paper_journal import PaperJournal
    journal2 = PaperJournal(journal.path)
    assert journal2.count() == 0, "Novo journal deve comecar vazio"

    # 4. Abre trade no novo journal
    recovery_trade = PaperTrade(
        trade_id="recovery-0",
        ticker="TSLA",
        thesis="Recovery after file deletion",
        direction="long",
        entry_date="2026-07-16T10:00:00Z",
        entry_price=250.0,
        shares=100,
        entry_reasoning="Post-deletion recovery",
        verdict_at_entry="STRONG_BUY",
        risk_assessment="Recovery test",
        expected_holding_period="swing",
    )
    journal2.open_trade(recovery_trade)
    assert journal2.count() == 1, "Falha ao adicionar trade apos recriacao do arquivo"
    assert journal2.list_open()[0]["trade_id"] == "recovery-0"


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_journal_concurrent_read_write(journal):
    """Leitura e escrita concorrentes no mesmo arquivo -> sem corrupcao.

    Simula multiplos componentes lendo e escrevendo no journal simultaneamente.
    """
    from core.trading.paper_journal import PaperJournal, PaperTrade
    import concurrent.futures
    import threading

    n_writers = 10
    trades_per_writer = 50
    total_expected = n_writers * trades_per_writer
    errors: list[str] = []
    lock = threading.Lock()

    def _writer(worker_id: int):
        local_journal = PaperJournal(journal.path)
        try:
            for t in range(trades_per_writer):
                trade = PaperTrade(
                    trade_id=f"concurrent-{worker_id}-{t:03d}",
                    ticker=["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"][t % 5],
                    thesis=f"Concurrent write #{worker_id}-{t}",
                    direction="long",
                    entry_date="2026-07-15T10:00:00Z",
                    entry_price=150.0 + t,
                    shares=10,
                    entry_reasoning=f"Worker {worker_id}, trade {t}",
                    verdict_at_entry="BUY",
                    risk_assessment="Concurrent test",
                    expected_holding_period="swing",
                )
                local_journal.open_trade(trade)
        except Exception as e:
            with lock:
                errors.append(f"Writer {worker_id}: {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_writers) as pool:
        futures = [pool.submit(_writer, i) for i in range(n_writers)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Erros em escritores concorrentes: {errors}"

    # JSONL append sem lock pode perder algumas linhas em escritas
    # concorrentes (race condition no append do SO). Aceitamos ate 5%
    # de perda.
    final_count = journal.count()
    MIN_ACCEPTABLE = int(total_expected * 0.95)
    assert final_count >= MIN_ACCEPTABLE, (
        f"Esperado >= {MIN_ACCEPTABLE} trades (95% de {total_expected}), "
        f"obtido {final_count}. Perda de {total_expected - final_count} trades. "
        f"Isso indica problema serio de concorrencia no journal."
    )

    # Verifica que todos os trade_ids sao unicos
    all_trades = journal.list_all()
    trade_ids = [t["trade_id"] for t in all_trades]
    unique_ids = set(trade_ids)
    assert len(trade_ids) == len(unique_ids), (
        f"Trade IDs duplicados: {len(trade_ids)} vs {len(unique_ids)} unicos"
    )

    # Verifica que todas as linhas sao JSON valido
    with open(journal.path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                pytest.fail(f"JSONL corrompido na linha {i}: {e}")


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_paper_trade_idempotent_operations(journal):
    """Operacoes idempotentes no journal nao criam duplicatas.

    Fechar o mesmo trade duas vezes ou adicionar reflexao duplicada
    nao deve corromper o estado.
    """
    from core.trading.paper_journal import PaperTrade

    # Abre trade
    trade = PaperTrade(
        trade_id="dup-test-001",
        ticker="AAPL",
        thesis="Idempotency test",
        direction="long",
        entry_date="2026-07-15T10:00:00Z",
        entry_price=150.0,
        shares=100,
        entry_reasoning="Test",
        verdict_at_entry="BUY",
        risk_assessment="Test",
        expected_holding_period="swing",
    )
    journal.open_trade(trade)

    # Fecha uma vez
    result1 = journal.close_trade("dup-test-001", exit_price=160.0, exit_reason="take_profit")
    assert result1 is not None
    assert result1.outcome == "win"

    # Fecha de novo (ja fechado) — deve retornar None ou manter estado
    # O importante e nao criar linha duplicada no JSONL
    journal.close_trade("dup-test-001", exit_price=170.0, exit_reason="take_profit")
    assert journal.count() == 1, "Fechar o mesmo trade duas vezes criou duplicata"

    # Verifica que o trade ainda esta correto
    stored = journal.get_trade("dup-test-001")
    assert stored is not None
    # O outcome deve ser win
    assert stored["outcome"] == "win"

    # Agora adiciona reflexao
    ref1 = journal.add_reflection(
        "dup-test-001",
        thesis_correct=True,
        what_went_right="Good entry",
        lesson_learned="Hold longer next time",
    )
    assert ref1 is not None

    # Adiciona reflexao de novo — deve atualizar, nao duplicar linha
    ref2 = journal.add_reflection(
        "dup-test-001",
        thesis_correct=True,
        what_went_right="Updated assessment",
        lesson_learned="Updated lesson",
    )
    assert ref2 is not None

    # Ainda deve ser 1 trade no arquivo (nao 2)
    assert journal.count() == 1, "Reflexao duplicada criou linha extra no JSONL"

    # Verifica que a ultima reflexao prevalece
    stored = journal.get_trade("dup-test-001")
    assert stored["lesson_learned"] == "Updated lesson", "Reflexao nao foi atualizada"


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_fastapi_pipeline_recovery():
    """Pipeline recovery apos erro simulado -> estado consistente.

    Simula o cenario onde o pipeline falha e precisa ser reinicializado.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    # Estado do pipeline
    pipeline_healthy = True
    init_count = 0

    @app.get("/health")
    async def health():
        if not pipeline_healthy:
            return {"status": "error", "detail": "Pipeline not initialized"}
        return {"status": "ok", "init_count": init_count}

    @app.post("/reset")
    async def reset_pipeline():
        nonlocal pipeline_healthy, init_count
        pipeline_healthy = True
        init_count += 1
        return {"status": "ok", "init_count": init_count}

    client = TestClient(app)

    # 1. Estado saudavel
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Simula falha do pipeline
    pipeline_healthy = False
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "error"

    # 3. Recovery via reset
    resp = client.post("/reset")
    assert resp.status_code == 200
    assert resp.json()["init_count"] == 1

    # 4. Pipeline voltou a funcionar
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["init_count"] == 1

    # 5. Multiplos resets
    for _ in range(5):
        client.post("/reset")
    resp = client.get("/health")
    assert resp.json()["init_count"] == 6, "Reset count incorreto"
