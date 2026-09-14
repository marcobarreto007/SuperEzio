"""Contract for /cockpit/summary ``deep`` — the fields that exist, and the ones
that do not.

History (2026-09-12): a 5s frontend poll read ``deep.f51`` / ``deep.sdca`` /
``deep.neural`` / ``deep.trinity`` / ``deep.guardrails``. Four of those five
keys were never published by this endpoint, so the poll only ever walked false
branches. The poll was removed, but the root cause — an undocumented ``deep``
contract that invited guessing — stayed. These tests pin the published schema
so the next reader does not have to guess.

They also pin the honest part: ``deep`` is filled for real by chat-stream
pipeline events (not "empty by design"), while ``guardrails`` genuinely is a
permanent empty stub.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

#: The concepts callers keep reaching for, and the names they guess for them.
GUESSED_NAMES = ("f51", "sdca", "neural", "trinity", "guardrails")

#: The only data-bearing keys `deep` is allowed to publish.
DEEP_DATA_FIELDS = ("last_math", "last_experts", "last_trinity")

_APP_STATE_ATTRS = (
    "last_math_report",
    "last_expert_verdicts",
    "last_trinity_report",
)


@pytest.fixture
def cockpit_client(monkeypatch):
    """TestClient with dev-anon auth and clean `deep` process state.

    The import runs before the env pinning because ``load_local_env()`` fires at
    import time and would otherwise reinstate the operator's PUBLIC_MODE/secret
    on top of the values set below (first request would 401). The `deep`
    counters live on ``app.state`` and survive across tests in a session, so
    they are cleared here and restored on teardown.
    """
    from agent_server.main import app

    monkeypatch.delenv("SUPEREZIO_JWT_SECRET", raising=False)
    monkeypatch.setenv("SUPEREZIO_PUBLIC_MODE", "0")
    monkeypatch.setenv("SUPEREZIO_OPEN_ACCESS", "0")

    saved = {name: getattr(app.state, name, _MISSING) for name in _APP_STATE_ATTRS}
    for name in _APP_STATE_ATTRS:
        if hasattr(app.state, name):
            delattr(app.state, name)

    yield app, TestClient(app)

    for name, value in saved.items():
        if value is _MISSING:
            if hasattr(app.state, name):
                delattr(app.state, name)
        else:
            setattr(app.state, name, value)


class _MISSING:
    """Sentinel: the attribute was absent before the test touched it."""


def _deep(client) -> dict:
    response = client.get("/cockpit/summary")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "deep" in body, f"no deep in summary; keys={list(body)}"
    return body


def test_deep_publishes_exactly_the_documented_fields(cockpit_client):
    """The schema is closed: three data fields plus the contract that names them."""
    _, client = cockpit_client
    deep = _deep(client)["deep"]

    assert set(deep) == set(DEEP_DATA_FIELDS) | {"contract"}, (
        f"deep drifted from its published schema: {sorted(deep)}"
    )


def test_deep_contract_names_every_real_field(cockpit_client):
    """`contract.fields` must describe exactly the data keys that exist."""
    _, client = cockpit_client
    contract = _deep(client)["deep"]["contract"]

    assert set(contract["fields"]) == set(DEEP_DATA_FIELDS)
    assert set(contract["populated"]) == set(DEEP_DATA_FIELDS)
    for key, spec in contract["fields"].items():
        assert spec.get("type"), f"{key} has no declared type"
        assert spec.get("from_event"), f"{key} does not name the event that fills it"
    assert contract["scope"], "contract must state the lifetime of the data"
    assert contract["filled_by"], "contract must name the producer"


def test_deep_contract_maps_guessed_names_to_a_real_path(cockpit_client):
    """Every name the old poll guessed must resolve to a path or say it has none."""
    _, client = cockpit_client
    body = _deep(client)
    contract = body["deep"]["contract"]

    for name in GUESSED_NAMES:
        assert name in contract["elsewhere"], (
            f"'{name}' was guessed by callers before — contract must place it"
        )

    # trinity and guardrails are published somewhere real: the pointer must hit.
    assert contract["elsewhere"]["trinity"] == "deep.last_trinity"
    assert "last_trinity" in body["deep"]
    assert contract["elsewhere"]["guardrails"].startswith("bob.guardrails")
    assert "guardrails" in body["bob"] and "guardrails" in body["status"]

    # f51 / sdca / neural are not published here — the contract has to say so
    # rather than leave a dangling name.
    for name in ("f51", "sdca", "neural"):
        assert "not published" in contract["elsewhere"][name]


def test_deep_starts_empty_and_flags_it_truthfully(cockpit_client):
    """A fresh process has no analysis yet: empty, and `populated` says so."""
    _, client = cockpit_client
    deep = _deep(client)["deep"]

    assert deep["last_math"] is None
    assert deep["last_experts"] == []
    assert deep["last_trinity"] == ""
    assert deep["contract"]["populated"] == {
        "last_math": False,
        "last_experts": False,
        "last_trinity": False,
    }


def test_deep_is_filled_for_real_by_pipeline_events(cockpit_client):
    """Decision pinned: these fields are real data, not an empty-by-design stub.

    _remember_cockpit_event is what runs on the live chat stream; drive it and
    the endpoint must report the payloads.
    """
    from agent_server.endpoints import _remember_cockpit_event

    app, client = cockpit_client
    request = SimpleNamespace(app=app)

    _remember_cockpit_event(request, {"type": "MATH_REPORT", "ticker": "MSFT", "sharpe": 1.31})
    _remember_cockpit_event(request, {"type": "EXPERT_DONE", "role": "risk"})
    _remember_cockpit_event(request, {"type": "TRINITY_DELIBERATION", "consensus": "WAIT"})

    deep = _deep(client)["deep"]
    assert deep["last_math"]["ticker"] == "MSFT"
    assert [e["role"] for e in deep["last_experts"]] == ["risk"]
    assert deep["last_trinity"]["consensus"] == "WAIT"
    assert deep["contract"]["populated"] == {
        "last_math": True,
        "last_experts": True,
        "last_trinity": True,
    }


def test_expert_verdicts_are_capped_at_twelve(cockpit_client):
    """`kept: 12` in the contract has to match what the recorder actually keeps."""
    from agent_server.endpoints import _remember_cockpit_event

    app, client = cockpit_client
    request = SimpleNamespace(app=app)
    for i in range(20):
        _remember_cockpit_event(request, {"type": "EXPERT_DONE", "role": f"e{i}"})

    deep = _deep(client)["deep"]
    assert len(deep["last_experts"]) == 12
    assert deep["contract"]["fields"]["last_experts"]["kept"] == 12
    assert deep["last_experts"][-1]["role"] == "e19", "must keep the newest, not the oldest"


def test_guardrails_is_a_documented_empty_stub(cockpit_client):
    """The other half of the decision: guardrails promises nothing and delivers
    nothing — deliberately, and now in writing.

    It takes no input and reads no state, so it cannot ever report a score. The
    contract marks it as a stub instead of letting a UI wait for `layers` to
    fill in.
    """
    from agent_server.endpoints import _cockpit_guardrail_summary

    _, client = cockpit_client
    body = _deep(client)

    for path in (body["bob"]["guardrails"], body["status"]["guardrails"]):
        assert path["ok"] is None
        assert path["total"] is None
        assert path["layers"] == []
        assert path["status"] == "unknown"
        assert path["evidence_at"] is None

    # Same object on every call, regardless of input.
    assert _cockpit_guardrail_summary() == _cockpit_guardrail_summary()

    assert "stub" in (_cockpit_guardrail_summary.__doc__ or "").lower(), (
        "a permanently empty contract must say so where the next reader looks"
    )
    assert "always empty" in body["deep"]["contract"]["elsewhere"]["guardrails"]
