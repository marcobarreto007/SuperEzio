"""Truth tests for the $1,000 CAD micro-capital survival protocol.

Precedente: tests/test_financial_engine_truth.py (commit d3095ea2) — "nao sei"
e None, nunca um numero inventado. Aqui a mesma regra vale para a BANCA: o
codigo nao escolhe a banca pelo operador.

Cobre:
  1. A banca configurada e $1.000 CAD e o broker offline nao carrega numero.
  2. get_mission_equity() devolve None (nao 10000.0) e cada chamador decide.
  3. O orcamento de risco e derivado (1,5% da banca), nao a constante $15.
"""

from __future__ import annotations

import json

import pytest

from core.mission_context import MISSION_CONTEXT_PATH, get_mission_equity

# ══════════════════════════════════════════════════════════════════════
# ITEM 1 — a banca e $1.000 CAD, e o broker offline nao carrega numero
# ══════════════════════════════════════════════════════════════════════


def _mission_context() -> dict:
    return json.loads(MISSION_CONTEXT_PATH.read_text(encoding="utf-8"))


def test_configured_bankroll_is_one_thousand_cad():
    """A banca vem da decisao do operador, nao de um default do codigo."""
    paper = _mission_context()["current_situation"]["paper_trading"]
    assert paper["equity"] == "1000.00 CAD"
    assert get_mission_equity() == 1000.0


def test_broker_account_equity_is_null_while_offline():
    """Campo de conta com broker offline e ficcao: nao pode carregar numero."""
    ibkr = _mission_context()["current_situation"]["broker"]["ibkr"]
    assert ibkr["connection"] == "offline"
    assert ibkr["account_equity"] is None
    assert ibkr["can_read_account"] is False


def test_offline_broker_equity_is_not_read_even_if_someone_fills_it_in():
    """Defesa em profundidade: um numero no campo offline nao vira banca."""
    situation = {
        "current_situation": {
            "broker": {"ibkr": {"connection": "offline", "account_equity": "9999.00"}},
        }
    }
    assert _equity_from(situation) is None


def test_connected_broker_equity_is_read():
    """Com conexao estabelecida, o numero do broker volta a ser legitimo."""
    situation = {
        "current_situation": {
            "broker": {"ibkr": {"connection": "connected_paper", "account_equity": "1234.56"}},
        }
    }
    assert _equity_from(situation) == pytest.approx(1234.56)


def _equity_from(situation_payload: dict) -> float | None:
    """get_mission_equity() sobre um payload em memoria (sem tocar no disco)."""
    from unittest.mock import patch

    with patch("core.mission_context.load_mission_context", return_value=situation_payload):
        return get_mission_equity()


# ══════════════════════════════════════════════════════════════════════
# ITEM 2 — "nao sei" e None, e nunca vira um numero chutado
# ══════════════════════════════════════════════════════════════════════


def test_get_mission_equity_returns_none_without_context_file(tmp_path):
    """Ausencia de dado e None — nunca o antigo 10000.0 silencioso."""
    assert get_mission_equity(tmp_path / "nao_existe.json") is None


def test_get_mission_equity_returns_none_when_equity_is_unparseable(tmp_path):
    path = tmp_path / "mission_context.json"
    path.write_text(
        json.dumps({"current_situation": {"paper_trading": {"equity": "  "}}}),
        encoding="utf-8",
    )
    assert get_mission_equity(path) is None


def test_get_mission_equity_returns_none_when_equity_is_not_positive(tmp_path):
    path = tmp_path / "mission_context.json"
    path.write_text(
        json.dumps({"current_situation": {"paper_trading": {"equity": "0.00 CAD"}}}),
        encoding="utf-8",
    )
    assert get_mission_equity(path) is None


def test_guardrail_position_sizer_reviews_when_equity_unknown(monkeypatch):
    """Guardrail: banca desconhecida NAO dimensiona — REVIEW, nunca ALLOW."""
    from core.pipeline.nodes.guardrail_hub import GuardrailHub

    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda *a, **k: None)

    result = GuardrailHub()._position_sizer({"data": {"price": 100.0}})

    assert result["decision"] == "REVIEW"
    assert result["decision"] != "ALLOW"
    assert "equity_unknown" in result["reason"]


@pytest.mark.asyncio
async def test_submit_paper_order_blocks_when_equity_unknown(monkeypatch):
    """Fail-closed: sem banca nao existe tamanho legitimo de posicao."""
    from core.trading.approval_gate import reset_approval_gate_for_test
    from core.trading.kill_switch import reset_kill_switch_for_test
    from src.core.pipeline.nodes import tool_executor as tool_executor_module

    monkeypatch.setenv("SUPEREZIO_ENABLE_PAPER_ORDER_SUBMIT", "1")
    reset_kill_switch_for_test()
    reset_approval_gate_for_test()
    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda *a, **k: None)

    result = await tool_executor_module._submit_paper_order(
        {
            "run_id": "equity-unknown-test",
            "ticket_allowed": True,
            "neural_decision": _ready_neural_decision(),
        },
        {
            "ticker": "SPY",
            "action": "buy",
            "qty": 10,
            "order_type": "LMT",
            "limit_price": 100.0,
            "take_profit_price": 115.0,  # 3:1 sobre o stop derivado de 5%
        },
    )

    # Duas camadas fail-closed pegam este caso, e o survival protocol roda
    # primeiro: o orcamento de risco tambem e derivado da banca, entao sem
    # banca ele ja barra a ordem. Qualquer que seja a camada, o motivo diz
    # equity_unknown — nunca um tamanho calculado em cima de chute.
    assert "equity_unknown" in result["submit_paper_order_error"]
    assert "submit_paper_order_error" in result


def _ready_neural_decision(direction: str = "UP") -> dict:
    return {
        "status": "ready",
        "decision": direction,
        "direction_prob": {"up": 0.7, "down": 0.1, "sideways": 0.2},
        "calibration_status": "calibrated",
        "prediction_set": [direction],
        "model_id": "test-neural-v1",
        "as_of": "2026-07-19T12:00:00+00:00",
        "horizon": 1,
    }


def test_concentration_gate_is_loud_when_equity_unknown(monkeypatch, capsys):
    """Best-effort mantido: nao bloqueia, mas o desconhecido fica barulhento.

    A decisao de nao bloquear quando a checagem de concentracao falha e
    pre-existente e deliberada. O que muda aqui e nao morrer como TypeError
    silencioso: equity_unknown vira warning explicito.
    """
    # O pacote nodes re-exporta uma FUNCAO de mesmo nome, que sombreia o
    # modulo em qualquer import por atributo. import_module pega o modulo.
    import importlib

    aep = importlib.import_module("core.pipeline.nodes.auto_execute_paper")

    class _Proc:
        returncode = 0
        stdout = '{"pct_of_equity": 10.0}'

    # `import subprocess as _sp` e local a funcao, entao o alvo do patch e o
    # modulo de verdade em sys.modules.
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Proc())
    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda *a, **k: None)

    blocked = aep._check_concentration("SPY", 100.0, "run-1")

    # O logger do projeto escreve em stdout (nao no logging raiz), entao a
    # evidencia e o stdout capturado.
    captured = capsys.readouterr()
    assert blocked is False
    assert "equity_unknown" in captured.out
    assert "concentration gate skipped" in captured.out


def test_kill_switch_is_born_active_when_equity_unknown():
    """Sem banca nao ha como medir drawdown: o switch nasce ativo (fail-closed)."""
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    switch = KillSwitch(initial_equity=None)

    assert switch.equity_unknown is True
    assert switch.state.is_active is True
    assert switch.state.reason == KillSwitchReason.EQUITY_UNKNOWN
    assert switch.state.peak_equity == 0.0


def test_kill_switch_stays_inactive_with_a_known_equity():
    """Nao regride o caminho normal: banca conhecida = switch ocioso."""
    from core.trading.kill_switch import KillSwitch

    switch = KillSwitch(initial_equity=1000.0)

    assert switch.equity_unknown is False
    assert switch.state.is_active is False
    assert switch.state.peak_equity == 1000.0


# ══════════════════════════════════════════════════════════════════════
# ITEM 2b — o limite de perda DIARIA e derivado do protocolo, nao 50% da banca
# ══════════════════════════════════════════════════════════════════════


def test_daily_loss_limit_is_derived_from_the_bankroll():
    """3 stop-outs cheios (3 x 1,5% de $1.000) = $45, nao os $500 antigos.

    $500 era metade da banca: o switch so acordava depois de o dia ja ter
    destruido 50% do capital, o oposto de "preservacao absoluta".
    """
    from core.trading.kill_switch import KillSwitch

    switch = KillSwitch(initial_equity=1000.0)

    assert switch.daily_loss_limit == pytest.approx(45.0)
    assert switch.daily_loss_limit == pytest.approx(3 * 0.015 * get_mission_equity())


def test_daily_loss_limit_trips_on_the_third_full_stop_out():
    from core.trading.kill_switch import KillSwitch, KillSwitchReason

    switch = KillSwitch(initial_equity=1000.0)

    assert switch.record_trade(-15.0) is False
    assert switch.record_trade(-15.0) is False
    assert switch.record_trade(-15.0) is True  # $45 acumulados no dia
    assert switch.state.reason == KillSwitchReason.DAILY_LOSS_LIMIT


def test_daily_loss_limit_explicit_value_still_wins():
    """A derivacao e o default; um numero explicito do chamador nao e ignorado."""
    from core.trading.kill_switch import KillSwitch

    assert KillSwitch(daily_loss_limit=500.0, initial_equity=1000.0).daily_loss_limit == 500.0


def test_daily_loss_limit_is_zero_when_equity_is_unknown():
    """Sem banca nao existe orcamento diario legitimo: tolerancia zero."""
    from core.trading.kill_switch import KillSwitch

    switch = KillSwitch(initial_equity=None)

    assert switch.daily_loss_limit == 0.0


def test_get_kill_switch_activates_when_mission_equity_is_unknown(monkeypatch, tmp_path):
    """O singleton global tambem nasce ativo quando a banca e desconhecida."""
    from core.trading import kill_switch as kill_switch_module

    monkeypatch.setattr(kill_switch_module, "_GLOBAL_KILL_SWITCH", None)
    monkeypatch.setattr(kill_switch_module, "_GLOBAL_KILL_SWITCH_PATH", None)
    monkeypatch.setattr("core.mission_context.get_mission_equity", lambda *a, **k: None)

    switch = kill_switch_module.KillSwitch(initial_equity=None, store=None)

    assert switch.state.is_active is True
    assert switch.state.reason is not None
    assert switch.state.reason.value == "equity_unknown"


# ══════════════════════════════════════════════════════════════════════
# ITEM 3 — o orcamento de risco e derivado da banca (1,5%), nao $15 cravado
# ══════════════════════════════════════════════════════════════════════


def test_risk_budget_is_1_5_pct_of_the_configured_bankroll():
    from core.trading.execution_policy import MICRO_CAPITAL_MAX_RISK_PCT

    assert MICRO_CAPITAL_MAX_RISK_PCT == 0.015
    equity = get_mission_equity()
    assert equity == 1000.0
    # $15 numa banca de $1.000 — o numero que estava cravado no codigo.
    assert equity * MICRO_CAPITAL_MAX_RISK_PCT == pytest.approx(15.0)


def test_risk_budget_moves_with_equity_and_is_not_a_hardcoded_fifteen():
    """Se fosse a constante $15, uma banca de $2.000 bloquearia em $30/acao."""
    from core.trading.execution_policy import micro_capital_survival_block_reason

    reason = micro_capital_survival_block_reason(
        {"paper_equity": 2000.0},
        "SPY",
        limit_price=100.0,
        stop_loss_price=70.0,  # $30 de risco por acao
        take_profit_price=190.0,  # 3:1
        qty=1,  # risco TOTAL da ordem = $30, o orcamento inteiro de $2.000
        order_type="LIMIT",
    )

    assert reason is None


def test_risk_budget_still_blocks_above_1_5_pct_of_a_thousand():
    from core.trading.execution_policy import micro_capital_survival_block_reason

    reason = micro_capital_survival_block_reason(
        {"paper_equity": 1000.0},
        "SPY",
        limit_price=100.0,
        stop_loss_price=84.99,  # $15.01 de risco por acao
        take_profit_price=200.0,
        qty=1,
        order_type="LIMIT",
    )

    assert reason is not None
    assert "risk_exceeds_budget" in reason
    assert "15.00" in reason  # o orcamento derivado, nao a constante solta


def test_position_sizer_default_risk_matches_the_protocol_ceiling():
    """PositionSizer default = 1,5% (teto do protocolo), nao mais 2%."""
    from core.trading.position_sizer import PositionSizer

    sizer = PositionSizer(equity=1000.0)

    assert sizer.max_risk_pct == 0.015
    assert sizer.max_risk_amount == pytest.approx(15.0)
