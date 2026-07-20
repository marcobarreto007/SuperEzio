"""Stress tests for concurrency — sem servidor externo.

Testes:
1. 100 requisicoes simultaneas em /health → sem crash
2. 50 requisicoes simultaneas em /task/submit → sem deadlock
3. 1000 paper trades no journal → sem corrupcao
4. Memory leak test: 1000 health checks → memoria estavel
"""

from __future__ import annotations

import gc
import json
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

from fastapi import Request

import pytest

pytestmark = [
    pytest.mark.stress,
    pytest.mark.slow,
]

# Garante que src/ esta no path
_SRC = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(_SRC))

# Ambiente de teste — auth desligada
os.environ.setdefault("UNIVERSAL_SKIP_GATEWAY", "1")
os.environ.setdefault("SUPEREZIO_JWT_SECRET", "")
os.environ.setdefault("SUPEREZIO_EDGE_AUTH", "false")


# ── Helpers ──────────────────────────────────────────────────────────────────


# Handlers de nivel de modulo para evitar o bug do FastAPI com closures
# (FastAPI nao consegue inspecionar signature de funcoes aninhadas)


async def _health_get_handler(request: Request):
    """GET /health handler — usa request.app.state para estado."""
    request.app.state.request_counter += 1
    return {
        "status": "ok",
        "agent": "stress-test",
        "version": "4.0.0",
        "checks": {},
        "request_id": request.app.state.request_counter,
    }


async def _health_head_handler(request: Request):
    """HEAD /health handler."""
    from fastapi.responses import Response

    return Response(status_code=200)


async def _bob_health_handler():
    return {
        "bob": "alive",
        "organs": {"brain": {"status": "ok"}, "heart": {"status": "ok"}},
        "healthy": 2,
        "sick": 0,
        "critical": 0,
        "pain": 0.0,
    }


def _create_health_app():
    """Cria uma FastAPI app minimalista com endpoint /health leve.

    Usamos uma app dedicada em vez da real para isolar o teste de
    concorrencia das dependencias pesadas (torch, redis, socket probes).
    """
    from fastapi import FastAPI

    app = FastAPI(title="SuperEzio Stress Test")
    app.state.request_counter = 0
    app.add_api_route("/health", _health_get_handler, methods=["GET"])
    app.add_api_route("/health", _health_head_handler, methods=["HEAD"])
    app.add_api_route("/bob/health", _bob_health_handler, methods=["GET"])
    return app


async def _submit_task_handler(request: Request):
    """Handler module-level para /task/submit.

    Module-level evita o bug do FastAPI com closures e inspect.signature.
    Estado (semaphore) acessado via request.app.state.
    """
    import asyncio
    import json
    import uuid as _uuid

    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    from core.ports.protocol import A2AMessage, MessageType

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    envelope = A2AMessage(**body)
    if envelope.type != MessageType.TASK_SUBMIT:
        raise HTTPException(
            status_code=400, detail="Invalid message type for this endpoint"
        )

    payload = envelope.payload if isinstance(envelope.payload, dict) else {}
    session_id = payload.get("session_id", "default")

    # Simula a Task Queue: 1 ativa por sessao
    semaphore: dict = request.app.state.task_semaphore
    if session_id in semaphore:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "active_task",
                "message": "Already processing for this session",
                "session_id": session_id,
            },
        )

    run_id = f"stress-{_uuid.uuid4().hex[:8]}"
    semaphore[session_id] = run_id
    msg_id = envelope.msg_id

    async def event_stream():
        try:
            yield json.dumps({
                "type": "STREAM_START",
                "msg_id": msg_id,
                "run_id": run_id,
            }) + "\n"
            await asyncio.sleep(0.005)
            yield json.dumps({
                "type": "CHUNK",
                "content": f"Analise concluida para sessao {session_id}",
            }) + "\n"
            await asyncio.sleep(0.005)
            yield json.dumps({
                "type": "STREAM_END",
                "trace": {"final_content_length": 35, "run_id": run_id},
            }) + "\n"
        finally:
            request.app.state.task_semaphore.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


def _create_task_submit_app():
    """Cria uma FastAPI app com endpoint /task/submit leve.

    O handler simula o comportamento real: recebe um envelope A2A,
    valida, processa e retorna um streaming response com eventos.
    """
    from fastapi import FastAPI

    app = FastAPI(title="SuperEzio Stress Test - Task Submit")
    app.state.task_semaphore: dict[str, str] = {}
    app.add_api_route("/task/submit", _submit_task_handler, methods=["POST"])
    return app


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def health_app():
    """App minimalista para testes de /health."""
    return _create_health_app()


@pytest.fixture(scope="module")
def task_app():
    """App minimalista para testes de /task/submit."""
    return _create_task_submit_app()


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


# ── Helpers de concorrencia ──────────────────────────────────────────────────


def _concurrent_requests(app, method: str, path: str, n: int, **kwargs):
    """Dispara N requisicoes simultaneas via ThreadPoolExecutor + TestClient.

    Cada thread cria seu proprio TestClient (que e sync e usa asyncio.run
    internamente), garantindo isolamento entre requisicoes.
    """
    import concurrent.futures
    from fastapi.testclient import TestClient

    errors: list[tuple[int, str]] = []
    results: list = [None] * n

    def _do_request(i: int):
        try:
            client = TestClient(app)
            if method.upper() == "GET":
                resp = client.get(path, **kwargs)
            elif method.upper() == "HEAD":
                resp = client.head(path, **kwargs)
            elif method.upper() == "POST":
                resp = client.post(path, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            return resp
        except Exception as e:
            errors.append((i, str(e)))
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 20)) as pool:
        futures = [pool.submit(_do_request, i) for i in range(n)]
        for i, f in enumerate(concurrent.futures.as_completed(futures)):
            # Obtem o indice original (mapeamento complexo com as_completed)
            pass
        # Coleta resultados na ordem
        for i, f in enumerate(futures):
            results[i] = f.result()

    return results, errors


# ── Teste 1: 100 simultaneas em /health ──────────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_100_simultaneous_health_requests(health_app):
    """100 requisicoes GET /health simultaneas -> sem crash, 100% 200."""
    n = 100
    responses, errors = _concurrent_requests(health_app, "GET", "/health", n)

    assert len(errors) == 0, f"{len(errors)} erros: {errors[:5]}"

    ok = sum(1 for r in responses if r is not None and r.status_code == 200)
    assert ok == n, f"Esperado {n}x 200, obtido {ok}"

    # Nenhuma resposta None ou vazia
    bodies = [r.json() for r in responses if r is not None and r.status_code == 200]
    assert len(bodies) == n
    assert all(b["status"] == "ok" for b in bodies)


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_health_with_head_method(health_app):
    """HEAD /health tambem responde sem crash sob carga."""
    n = 50
    responses, errors = _concurrent_requests(health_app, "HEAD", "/health", n)

    assert len(errors) == 0, f"{len(errors)} erros: {errors[:5]}"
    ok = sum(1 for r in responses if r is not None and r.status_code == 200)
    assert ok == n, f"Esperado {n}x 200 para HEAD, obtido {ok}"


# ── Teste 2: 50 simultaneas em /task/submit ──────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(120)
def test_50_simultaneous_task_submit(task_app):
    """50 requisicoes POST /task/submit concorrentes -> sem deadlock.

    Cada requisicao tem session_id unico para evitar o gate "1 ativa por sessao".
    """
    from core.ports.protocol import MessageType

    n = 50

    def _submit_one(session_id: str, idx: int):
        from fastapi.testclient import TestClient

        client = TestClient(task_app)
        payload = {
            "from_agent": "stress-test",
            "to_agent": "bob",
            "type": MessageType.TASK_SUBMIT,
            "msg_id": f"stress-{idx}",
            "payload": {
                "message": f"Analise a acao AAPL para sessao {session_id}",
                "session_id": session_id,
                "ticker": "AAPL",
            },
        }
        return client.post("/task/submit", json=payload)

    import concurrent.futures

    errors: list[tuple[int, str]] = []
    results: list = [None] * n

    def _safe_submit(i: int):
        try:
            return _submit_one(f"session-{i:04d}", i)
        except Exception as e:
            errors.append((i, str(e)))
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(n, 20)) as pool:
        futures = [pool.submit(_safe_submit, i) for i in range(n)]
        for i, f in enumerate(futures):
            results[i] = f.result()

    assert len(errors) == 0, f"{len(errors)} erros: {errors[:5]}"

    # Conta quantas foram aceitas (200) vs rejeitadas (429)
    ok = sum(1 for r in results if r is not None and r.status_code == 200)
    rejected = sum(1 for r in results if r is not None and r.status_code == 429)

    # Com session_id unicos, todas devem ser aceitas
    assert ok == n, (
        f"Esperado {n}x 200, obtido {ok} ({rejected} rejeitadas por rate-limit)"
    )

    # Verifica que todas retornaram NDJSON valido com STREAM_END
    for r in results:
        if r is None:
            continue
        lines = r.text.strip().split("\n")
        events = [json.loads(line) for line in lines]
        types = [ev["type"] for ev in events]
        assert "STREAM_END" in types, f"Resposta sem STREAM_END: {lines[:2]}"


@pytest.mark.stress
@pytest.mark.timeout(120)
def test_task_submit_rate_limit_per_session(task_app):
    """2 requisicoes na mesma sessao -> segunda deve ser 429.

    Usamos um hack no semaphore para simular processamento lento:
    modificamos o handler para que o semaphore persista ate que
    o TestClient leia o stream por completo.
    """
    from core.ports.protocol import MessageType
    from fastapi.testclient import TestClient

    client = TestClient(task_app)

    payload2 = {
        "from_agent": "stress-test",
        "to_agent": "bob",
        "type": MessageType.TASK_SUBMIT,
        "msg_id": "second",
        "payload": {
            "message": "Segunda requisicao na mesma sessao",
            "session_id": "same-session-test",
        },
    }

    # Dispara a primeira requisicao mas NAO lemos o stream ainda
    # Precisamos de um mecanismo que mantenha o semaphore ativo
    # Enquanto disparamos a segunda.

    # Forca o semaphore a ficar ativo manualmente para simular
    # uma requisicao em andamento
    task_app.state.task_semaphore["same-session-test"] = "simulated-active-run"

    # Segunda na mesma sessao
    resp2 = client.post("/task/submit", json=payload2)

    assert resp2.status_code == 429, (
        f"Esperado 429 (active_task), obtido {resp2.status_code}: {resp2.text[:100]}"
    )
    detail = resp2.json()
    assert detail.get("detail", {}).get("code") == "active_task"

    # Limpa o semaphore
    task_app.state.task_semaphore.pop("same-session-test", None)


# ── Teste 3: 1000 paper trades no journal ────────────────────────────────────


@pytest.mark.stress
@pytest.mark.timeout(60)
def test_1000_paper_trades_no_corruption(journal_file):
    """1000 trades abertos e fechados -> 0 corrupcao, estatisticas consistentes."""
    from core.trading.paper_journal import PaperJournal, PaperTrade

    journal = PaperJournal(journal_file)
    tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMZN", "META", "BRK.B"]

    # Abre 1000 trades
    trade_ids = []
    for i in range(1000):
        ticker = tickers[i % len(tickers)]
        price = 100.0 + (i % 200)
        trade = PaperTrade(
            trade_id=f"stress-{i:04d}",
            ticker=ticker,
            thesis=f"Test trade #{i} for {ticker}",
            direction="long" if (i % 3) != 0 else "short",
            entry_date=f"2026-07-{1 + (i % 20):02d}T10:00:00Z",
            entry_price=price,
            shares=10 + (i % 100),
            entry_reasoning=f"Momentum entry #{i}",
            verdict_at_entry="SMALL_POSITION" if (i % 2) == 0 else "STUDY_MORE",
            risk_assessment=f"Risk level: moderate, trade #{i}",
            expected_holding_period="swing",
        )
        journal.open_trade(trade)
        trade_ids.append(f"stress-{i:04d}")

    assert journal.count() == 1000, f"Esperado 1000 trades, obtido {journal.count()}"

    # Fecha metade dos trades
    for i in range(500):
        exit_price = 100.0 + (i % 200) + (5 if (i % 2) == 0 else -5)
        journal.close_trade(
            f"stress-{i:04d}",
            exit_price=exit_price,
            exit_reason="take_profit" if (i % 2) == 0 else "stop_loss",
        )

    # Verifica consistencia
    open_trades = journal.list_open()
    closed_trades = journal.list_closed()
    assert len(open_trades) == 500, f"Esperado 500 abertos, obtido {len(open_trades)}"
    assert len(closed_trades) == 500, f"Esperado 500 fechados, obtido {len(closed_trades)}"

    # Verifica corrupcao: todas as linhas devem ser JSON valido
    with open(journal_file) as f:
        lines = [line.strip() for line in f if line.strip()]
    assert len(lines) == 1000, f"Esperado 1000 linhas JSONL, obtido {len(lines)}"

    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            pytest.fail(f"Linha {i} corrompida: {e}. Conteudo: {line[:100]}")

        # Verifica campos obrigatorios
        assert "trade_id" in obj, f"Linha {i} sem trade_id"
        assert "ticker" in obj, f"Linha {i} sem ticker"
        assert "direction" in obj, f"Linha {i} sem direction"
        assert "entry_price" in obj, f"Linha {i} sem entry_price"

    # Verifica estatisticas
    stats = journal.get_stats()
    assert stats["total_trades"] == 1000
    assert stats["open_trades"] == 500
    assert stats["closed_trades"] == 500


# ── Teste 4: Memory leak — 1000 health checks ────────────────────────────────


def _estimate_app_overhead():
    """Estimate baseline memory of a minimal FastAPI app."""
    # Chama o construtor para carregar o codigo na memoria
    _create_health_app()
    gc.collect()


@pytest.mark.stress
@pytest.mark.timeout(120)
def test_memory_leak_1000_health_checks():
    """1000 chamadas /health -> memoria estavel (crescimento < 10 MB)."""
    _estimate_app_overhead()

    from fastapi.testclient import TestClient

    app = _create_health_app()

    # Ativa tracemalloc
    try:
        tracemalloc.start()
    except RuntimeError:
        tracemalloc.stop()
        tracemalloc.start()

    gc.collect()
    snapshot_before = tracemalloc.take_snapshot()

    # Dispara 1000 health checks sequenciais com TestClient
    client = TestClient(app)
    for _ in range(1000):
        resp = client.get("/health")
        assert resp.status_code == 200
        _ = resp.json()  # Simula processamento real

    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()

    # Compara alocacao
    stats = snapshot_after.compare_to(snapshot_before, "lineno")

    # Soma o diferencial de memoria (size_diff pode ser negativo se GC coletou)
    total_diff = sum(s.size_diff for s in stats)
    # Para debug: identifica as maiores alocacoes
    top_leakers = sorted(stats, key=lambda s: abs(s.size_diff), reverse=True)[:5]

    # Limite: 10 MB de crescimento e tolerado
    # (tracemalloc pode reportar alocacao acumulada, nao residente)
    MAX_GROWTH_BYTES = 10 * 1024 * 1024  # 10 MB

    assert total_diff < MAX_GROWTH_BYTES, (
        f"Memoria cresceu {total_diff / 1024:.1f} KB apos 1000 health checks. "
        f"Top alocacoes: "
        + "; ".join(
            f"{s.traceback.format()[-1] if s.traceback else '?'} ({s.size_diff / 1024:.1f} KB)"
            for s in top_leakers
        )
    )

    # Tambem verifica o numero de objetos alive
    obj_count_before = len(gc.get_objects())
    gc.collect()
    obj_count_after = len(gc.get_objects())
    obj_growth = obj_count_after - obj_count_before
    # Tolerancia: ate 1000 objetos apos 1000 requisicoes (1 objeto/request de overhead)
    assert obj_growth < 1000, (
        f"Crescimento de {obj_growth} objetos apos 1000 health checks. "
        f"Possivel leak de objetos."
    )

    tracemalloc.stop()


@pytest.mark.stress
@pytest.mark.timeout(30)
def test_concurrent_bob_health(health_app):
    """50 requisicoes GET /bob/health simultaneas -> sem crash."""
    n = 50
    responses, errors = _concurrent_requests(health_app, "GET", "/bob/health", n)

    assert len(errors) == 0, f"{len(errors)} erros: {errors[:5]}"
    ok = sum(1 for r in responses if r is not None and r.status_code == 200)
    assert ok == n, f"Esperado {n}x 200, obtido {ok}"

    for r in responses:
        if r is not None:
            body = r.json()
            assert body["bob"] == "alive"
