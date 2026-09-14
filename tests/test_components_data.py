"""Component tests: Data Providers, Model Serving, Agent Server, Config."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ── Config: model_manifest.json ──
def test_model_manifest_exists():
    manifest_path = ROOT / "config" / "model_manifest.json"
    assert manifest_path.exists(), f"model_manifest.json not found at {manifest_path}"


def test_model_manifest_agent():
    from core.model_serving.providers import BRAIN_MODEL_ID

    manifest_path = ROOT / "config" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "agent" in manifest
    # Deciding role (2026-09-12): Bob/CEO declares the brain model.
    assert manifest["agent"]["model"] == BRAIN_MODEL_ID
    assert manifest["agent"]["base_model"] == BRAIN_MODEL_ID
    assert manifest["agent"]["backend"] == "openai_compatible"
    assert manifest["agent"]["server_url"].startswith("https://api.deepseek.com")


def test_model_manifest_providers():
    from core.model_serving.providers import BRAIN_MODEL_ID, DEEPSEEK_MODEL_ID

    manifest_path = ROOT / "config" / "model_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "providers" in manifest
    assert "local_orchestrator" in manifest["providers"]
    assert manifest["providers"]["glm"]["base_url"] == "https://api.z.ai/api/coding/paas/v4"
    assert manifest["providers"]["glm"]["model"] == "glm-5.3"
    assert manifest["providers"]["glm"]["allow_fallback"] is False
    # Deciding role (2026-09-12): the orchestrator declares the brain model.
    assert manifest["providers"]["local_orchestrator"]["model"] == BRAIN_MODEL_ID
    # Supporting role: the expert committee stays on flash.
    assert manifest["providers"]["deepseek"]["base_url"] == "https://api.deepseek.com"
    assert manifest["providers"]["deepseek"]["model"] == DEEPSEEK_MODEL_ID
    assert manifest["providers"]["deepseek"]["allow_fallback"] is False


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
    assert gc.timeout_s == 300  # GatewayConfig default: 300s (increased from 120)
    assert gc.retry_attempts == 2


def test_provider_constants():
    from core.model_serving.providers import (
        AGENT_MODEL_ID,
        AGENT_PROVIDER_NAME,
        BRAIN_MODEL_ID,
        DEEPSEEK_MODEL_ID,
        DEEPSEEK_OFFICIAL_MODELS,
        DEEPSEEK_PROVIDER_NAME,
        GLM_PROVIDER_NAME,
        PRIMARY_MODEL_ID,
        PRIMARY_PROVIDER_NAME,
    )

    assert AGENT_PROVIDER_NAME == "agent"
    assert PRIMARY_PROVIDER_NAME == "local_orchestrator"
    assert DEEPSEEK_PROVIDER_NAME == "deepseek"
    assert GLM_PROVIDER_NAME == "glm"
    # Decisao de 2026-09-12: quem DECIDE (CEO/agent e orquestrador) roda o
    # modelo mais forte; os papeis de APOIO ficam no mais leve. Ambos os IDs
    # sao oficiais (DEEPSEEK_OFFICIAL_MODELS).
    assert AGENT_MODEL_ID == BRAIN_MODEL_ID
    assert PRIMARY_MODEL_ID == BRAIN_MODEL_ID
    assert BRAIN_MODEL_ID != DEEPSEEK_MODEL_ID
    assert BRAIN_MODEL_ID in DEEPSEEK_OFFICIAL_MODELS
    assert DEEPSEEK_MODEL_ID in DEEPSEEK_OFFICIAL_MODELS


def test_provider_boundaries_and_credentials(monkeypatch):
    """DeepSeek serves every role (brain on pro, support on flash); the optional
    GLM path stays isolated."""
    from core.config import reload_config
    from core.model_serving.providers import (
        BRAIN_MODEL_ID,
        DEEPSEEK_MODEL_ID,
        build_default_providers,
    )

    monkeypatch.delenv("SUPEREZIO_AGENT_API_KEY", raising=False)
    import core.config.secrets as _secrets

    monkeypatch.setattr(_secrets, "load_local_env", lambda: None)
    monkeypatch.delenv("SUPEREZIO_AGENT_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_PRIMARY_API_KEY", raising=False)
    monkeypatch.setenv("SUPEREZIO_GLM_CODING_PLAN_API_KEY", "test-glm-secret")
    monkeypatch.setenv("SUPEREZIO_DEEPSEEK_API_KEY", "test-deepseek-secret")
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("SUPEREZIO_DAYTRADE_AUDITOR_MODEL", raising=False)
    cfg = reload_config()
    providers, _ = build_default_providers(cfg)

    assert providers, "build_default_providers retornou lista vazia"
    by_name = {p.name: p for p in providers}
    for name in ("agent", "local_orchestrator", "deepseek", "daytrade_judge", "daytrade_auditor"):
        p = by_name[name]
        assert p.is_local is False
        assert p.base_url == "https://api.deepseek.com"
        assert p.api_key == "test-deepseek-secret"
    # Papeis de cerebro (decisao de 2026-09-12): o modelo mais forte decide.
    for name in ("agent", "local_orchestrator"):
        assert by_name[name].model == BRAIN_MODEL_ID
    # Papeis de apoio: os experts, o judge e o auditor continuam no flash.
    for name in ("deepseek", "daytrade_judge", "daytrade_auditor"):
        assert by_name[name].model == DEEPSEEK_MODEL_ID
    # O caminho GLM e opcional: existe aqui so porque o teste arma a chave.
    glm = by_name["glm"]
    assert glm.is_local is False
    assert glm.base_url == "https://api.z.ai/api/coding/paas/v4"
    assert glm.model == "glm-5.3"
    assert glm.api_key == "test-glm-secret"


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
    """Facade removido — importa direto do canon."""
    from core.ports.protocol import A2AMessage, MessageType

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
