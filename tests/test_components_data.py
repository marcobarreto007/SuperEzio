"""Component tests: Data Providers, Model Serving, Agent Server, Config."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── Config: model_manifest.json ──
def test_model_manifest_exists():
    manifest_path = ROOT / "config" / "model_manifest.json"
    assert manifest_path.exists(), f"model_manifest.json not found at {manifest_path}"


def test_model_manifest_ceo():
    manifest_path = ROOT / "config" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "ceo" in manifest
    assert manifest["ceo"]["model"] == "gemma-4-26b-abliterated"
    assert manifest["ceo"]["backend"] == "openai_compatible"


def test_model_manifest_cloud_models():
    manifest_path = ROOT / "config" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "cloud_models" in manifest
    assert "primary_external" in manifest["cloud_models"]


def test_model_manifest_expert_runtime():
    manifest_path = ROOT / "config" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "expert_runtime" in manifest
    assert len(manifest["expert_runtime"]["roles"]) >= 10


# ── Config: mandamentos.json ──
def test_mandamentos_exists():
    m_path = ROOT / "config" / "mandamentos.json"
    assert m_path.exists()


def test_mandamentos_valid_json():
    m_path = ROOT / "config" / "mandamentos.json"
    data = json.loads(m_path.read_text(encoding="utf-8"))
    assert isinstance(data, (list, dict))


# ── Model Serving: Providers ──
def test_model_provider_dataclass():
    from core.model_serving.providers import ModelProvider

    mp = ModelProvider(
        name="test_provider",
        base_url="http://localhost:8080/v1",
        api_key="sk-test",
    )
    assert mp.name == "test_provider"
    assert mp.priority == 0
    assert mp.is_local is False


def test_gateway_config_defaults():
    from core.model_serving.providers import GatewayConfig

    gc = GatewayConfig()
    assert gc.max_fallbacks == 2
    assert gc.timeout_s == 120
    assert gc.retry_attempts == 2


def test_provider_constants():
    from core.model_serving.providers import (
        CEO_PROVIDER_NAME,
        CEO_MODEL_ID,
        PRIMARY_PROVIDER_NAME,
        DEEPSEEK_PROVIDER_NAME,
    )

    assert CEO_PROVIDER_NAME == "ceo"
    assert CEO_MODEL_ID == "qwen36-35b-f51"
    assert PRIMARY_PROVIDER_NAME == "primary_external"
    assert DEEPSEEK_PROVIDER_NAME == "deepseek"


# ── Model Serving: Sanitizer ──
def test_strip_private_model_channels():
    from core.model_serving.sanitizer import strip_private_model_channels

    assert strip_private_model_channels("") == ""
    assert strip_private_model_channels("normal text") == "normal text"


def test_strip_think_blocks():
    from core.model_serving.sanitizer import strip_private_model_channels

    text = "Hello <think>secret reasoning</think> world"
    result = strip_private_model_channels(text)
    assert "secret reasoning" not in result
    assert "Hello" in result
    assert "world" in result


def test_strip_channel_tokens():
    from core.model_serving.sanitizer import strip_private_model_channels

    # Private channel content gets stripped; visible-only text remains
    result = strip_private_model_channels(
        "visible text <|channel|>thought\ndanger analysis<|message|>"
    )
    assert "visible text" in result
    assert "danger analysis" not in result  # private channel stripped


def test_private_channel_filter():
    from core.model_serving.sanitizer import PrivateChannelFilter

    f = PrivateChannelFilter()
    assert f is not None


def test_sanitizer_no_crash_on_none():
    from core.model_serving.sanitizer import strip_private_model_channels

    result = strip_private_model_channels(None)
    assert result is None


# ── Agent Server: Protocol ──
def test_a2a_protocol_import():
    from agent_server.protocol import A2AMessage, MessageType

    assert MessageType is not None
    assert A2AMessage is not None


def test_a2a_message_types():
    from core.ports.protocol import MessageType

    assert hasattr(MessageType, "TASK_SUBMIT")
    assert hasattr(MessageType, "TASK_RESULT")
    assert hasattr(MessageType, "ERROR")


# ── Data Hub ──
def test_data_hub_import():
    from data.data_hub import DataHub

    assert DataHub is not None


def test_data_hub_provider_list():
    from data.data_hub import DataHub

    hub = DataHub()
    active = hub.list_active()
    assert isinstance(active, list)


def test_data_hub_check_health():
    from data.data_hub import DataHub

    hub = DataHub()
    health = hub.check_health()
    assert isinstance(health, dict)
    assert "providers" in health


# ── Data Providers: imports only (network-dependent, only verify importability) ──
def test_alpha_vantage_import():
    from data.alpha_vantage import AlphaVantageProvider

    p = AlphaVantageProvider(api_key="test")
    assert p is not None


def test_twelve_data_import():
    from data.twelve_data import TwelveDataProvider

    p = TwelveDataProvider(api_key="test")
    assert p is not None


def test_news_feed_import():
    from data.news_feed import NewsScout

    ns = NewsScout()
    assert ns is not None


def test_reddit_provider_import():
    from data.reddit_provider import RedditPulse

    rp = RedditPulse()
    assert rp is not None


def test_boc_provider_import():
    from data.boc_provider import get_macro_summary_ca

    assert get_macro_summary_ca is not None


def test_fed_provider_import():
    from data.fed_provider import get_macro_summary_us

    assert get_macro_summary_us is not None


# ── Model Gateway ──
def test_model_gateway_import():
    from core.model_serving.gateway import ModelGateway

    assert ModelGateway is not None


def test_model_gateway_instantiate():
    from core.model_serving.gateway import ModelGateway
    from core.model_serving.providers import GatewayConfig

    gw = ModelGateway(providers=[], config=GatewayConfig())
    assert gw is not None
    assert gw.config.max_fallbacks == 2


print("Data Providers + Model Serving + Agent Server + Config: ALL TESTS PASSED")
