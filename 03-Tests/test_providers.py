"""
Behavioral tests for the cloud provider adapters (audit 009 #7, #8).

Before this file the three cloud adapters (Anthropic / OpenAI / Vertex) got ZERO
execution in any CI job — `test_router.py` only asserted `isinstance` + field
values, so `generate_with_messages`, the retry logic, and the embed paths (the
exact code the PolicyEngine trusts on every outbound call) were never run.

These tests mock the *SDK boundary* (the lazily-imported `anthropic` / `openai` /
`vertexai` modules) via `sys.modules` injection and exercise the provider's own
real logic against it. No network, no cloud SDK installed, runs in the blocking
unit gate. This also raises provider coverage from ~20% → high, which mechanically
drops the CRAP hotspots (CRAP = complexity² · (1−coverage)³ + complexity).

`test_provider_contract` is the ABC contract (#8): every concrete provider's
locality classification and never-raising `health_check` — the guarantees the
policy gate depends on for its local/cloud decision.
"""
import sys
import types

import pytest

from nexus.core.config import Config
from nexus.core.providers.anthropic_provider import AnthropicLLMProvider
from nexus.core.providers.base import EmbeddingProvider, LLMProvider
from nexus.core.providers.ollama_provider import OllamaEmbeddingProvider, OllamaLLMProvider
from nexus.core.providers.openai_provider import (
    OpenAICompatibleLLMProvider,
    OpenAIEmbeddingProvider,
    OpenAILLMProvider,
)
from nexus.core.providers.profiles import ProviderHealth
from nexus.core.providers.vertex_provider import VertexEmbeddingProvider, VertexLLMProvider


# --------------------------------------------------------------------------- #
# Helpers — inject fake SDK modules the providers import lazily.
# --------------------------------------------------------------------------- #
def _install(monkeypatch, name, module):
    monkeypatch.setitem(sys.modules, name, module)


def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def _no_sleep(monkeypatch, module_path):
    monkeypatch.setattr(f"{module_path}.time.sleep", lambda *a, **k: None)


def _raise(*a, **k):
    raise RuntimeError("boom")


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
def _fake_anthropic(create_fn):
    class FakeAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.messages = types.SimpleNamespace(create=create_fn)

    return _mod("anthropic", Anthropic=FakeAnthropic)


def _anthropic_reply(text):
    return types.SimpleNamespace(content=[types.SimpleNamespace(text=text)])


class TestAnthropicProvider:
    def test_generate_with_messages_success(self, monkeypatch):
        _install(monkeypatch, "anthropic", _fake_anthropic(lambda **k: _anthropic_reply("ANSWER")))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        assert p.generate_with_messages([{"role": "user", "content": "hi"}]) == "ANSWER"

    def test_generate_delegates_to_messages(self, monkeypatch):
        _install(monkeypatch, "anthropic", _fake_anthropic(lambda **k: _anthropic_reply("VIA_GENERATE")))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        assert p.generate("hi") == "VIA_GENERATE"

    def test_extracts_system_message(self, monkeypatch):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return _anthropic_reply("OK")

        _install(monkeypatch, "anthropic", _fake_anthropic(create))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        p.generate_with_messages(
            [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
        )
        assert captured["system"] == "be terse"
        assert all(m["role"] != "system" for m in captured["messages"])

    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        _no_sleep(monkeypatch, "nexus.core.providers.anthropic_provider")
        seq = iter(
            [Exception("429 rate limit"), Exception("429 rate limit"), _anthropic_reply("RECOVERED")]
        )

        def create(**kwargs):
            item = next(seq)
            if isinstance(item, Exception):
                raise item
            return item

        _install(monkeypatch, "anthropic", _fake_anthropic(create))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        assert p.generate_with_messages([{"role": "user", "content": "hi"}]) == "RECOVERED"

    def test_rate_limit_exhausted_raises(self, monkeypatch):
        _no_sleep(monkeypatch, "nexus.core.providers.anthropic_provider")

        def create(**kwargs):
            raise Exception("429 too many requests")

        _install(monkeypatch, "anthropic", _fake_anthropic(create))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            p.generate_with_messages([{"role": "user", "content": "hi"}])

    def test_non_retryable_error_propagates(self, monkeypatch):
        def create(**kwargs):
            raise KeyError("bad request")

        _install(monkeypatch, "anthropic", _fake_anthropic(create))
        p = AnthropicLLMProvider(api_key="sk-ant-test")
        with pytest.raises(KeyError):
            p.generate_with_messages([{"role": "user", "content": "hi"}])

    def test_is_available_true_when_sdk_present(self, monkeypatch):
        _install(monkeypatch, "anthropic", _fake_anthropic(lambda **k: _anthropic_reply("x")))
        assert AnthropicLLMProvider(api_key="sk-ant-test").is_available() is True

    def test_is_available_false_on_missing_sdk(self, monkeypatch):
        _install(monkeypatch, "anthropic", None)  # None in sys.modules -> ImportError on import
        assert AnthropicLLMProvider(api_key="sk-ant-test").is_available() is False

    def test_missing_key_raises_at_construction(self, monkeypatch):
        monkeypatch.setattr(Config, "ANTHROPIC_API_KEY", "")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY required"):
            AnthropicLLMProvider()


# --------------------------------------------------------------------------- #
# OpenAI (Chat Completions, Responses API, embeddings) + OpenAI-compatible
# --------------------------------------------------------------------------- #
def _fake_openai(chat_create=None, responses_create=None, embeddings_create=None):
    class FakeOpenAI:
        def __init__(self, api_key=None, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=chat_create)
            )
            self.responses = types.SimpleNamespace(create=responses_create)
            self.embeddings = types.SimpleNamespace(create=embeddings_create)

    return _mod("openai", OpenAI=FakeOpenAI)


def _openai_chat_reply(text):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))]
    )


class TestOpenAIProvider:
    def test_chat_completions_success(self, monkeypatch):
        _install(monkeypatch, "openai", _fake_openai(chat_create=lambda **k: _openai_chat_reply("ANSWER")))
        p = OpenAILLMProvider(api_key="sk-test")
        assert p.generate_with_messages([{"role": "user", "content": "hi"}]) == "ANSWER"

    def test_responses_api_path(self, monkeypatch):
        _install(
            monkeypatch,
            "openai",
            _fake_openai(responses_create=lambda **k: types.SimpleNamespace(output_text="VIA_RESPONSES")),
        )
        p = OpenAILLMProvider(api_key="sk-test", use_responses_api=True)
        assert p.generate("hi") == "VIA_RESPONSES"

    def test_chat_retries_then_raises(self, monkeypatch):
        _no_sleep(monkeypatch, "nexus.core.providers.openai_provider")

        def chat(**kwargs):
            raise Exception("429 rate limited")

        _install(monkeypatch, "openai", _fake_openai(chat_create=chat))
        p = OpenAILLMProvider(api_key="sk-test")
        with pytest.raises(ValueError, match="API error after"):
            p.generate_with_messages([{"role": "user", "content": "hi"}])

    def test_non_retryable_error_propagates(self, monkeypatch):
        def chat(**kwargs):
            raise KeyError("nope")

        _install(monkeypatch, "openai", _fake_openai(chat_create=chat))
        p = OpenAILLMProvider(api_key="sk-test")
        with pytest.raises(KeyError):
            p.generate_with_messages([{"role": "user", "content": "hi"}])

    def test_embed_documents_and_query(self, monkeypatch):
        def emb(**kwargs):
            inp = kwargs["input"]
            n = 1 if isinstance(inp, str) else len(inp)  # API accepts str or list
            return types.SimpleNamespace(
                data=[types.SimpleNamespace(embedding=[0.1, 0.2, 0.3]) for _ in range(n)]
            )

        _install(monkeypatch, "openai", _fake_openai(embeddings_create=emb))
        p = OpenAIEmbeddingProvider(api_key="sk-test")
        assert p.embed_documents(["a", "b"]) == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
        assert p.embed_query("q") == [0.1, 0.2, 0.3]

    def test_is_available_false_on_missing_sdk(self, monkeypatch):
        _install(monkeypatch, "openai", None)
        assert OpenAILLMProvider(api_key="sk-test").is_available() is False


class TestOpenAICompatibleProvider:
    def test_requires_base_url(self, monkeypatch):
        monkeypatch.setattr(Config, "OPENAI_COMPATIBLE_BASE_URL", None)
        with pytest.raises(ValueError, match="base_url required"):
            OpenAICompatibleLLMProvider(model="m")

    def test_requires_model(self, monkeypatch):
        monkeypatch.setattr(Config, "OPENAI_COMPATIBLE_MODEL", None)
        with pytest.raises(ValueError, match="model required"):
            OpenAICompatibleLLMProvider(base_url="http://localhost:1234/v1")

    def test_generate_and_declared_locality(self, monkeypatch):
        _install(monkeypatch, "openai", _fake_openai(chat_create=lambda **k: _openai_chat_reply("COMPAT")))
        p = OpenAICompatibleLLMProvider(base_url="http://localhost:1234/v1", model="m", is_local=True)
        assert p.generate("hi") == "COMPAT"
        # A self-hosted endpoint declared local must classify as on-host.
        assert p.get_privacy_profile().is_local is True

    def test_defaults_to_not_local(self, monkeypatch):
        p = OpenAICompatibleLLMProvider(base_url="https://openrouter.ai/api/v1", model="m")
        assert p.get_privacy_profile().is_local is False  # fail-closed default


# --------------------------------------------------------------------------- #
# Vertex AI (Gemini generate + textembedding-gecko)
# --------------------------------------------------------------------------- #
def _install_vertex(monkeypatch, *, generate_text="ANSWER", embed_values=None):
    aiplatform = _mod("google.cloud.aiplatform", init=lambda **k: None)
    google_cloud = _mod("google.cloud", aiplatform=aiplatform)
    google = _mod("google", cloud=google_cloud)
    _install(monkeypatch, "google", google)
    _install(monkeypatch, "google.cloud", google_cloud)
    _install(monkeypatch, "google.cloud.aiplatform", aiplatform)

    class FakeGenModel:
        def __init__(self, model, system_instruction=None):
            self.model = model
            self.system_instruction = system_instruction

        def generate_content(self, content, generation_config=None):
            return types.SimpleNamespace(text=generate_text)

    class FakeGenConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    genmod = _mod(
        "vertexai.generative_models", GenerativeModel=FakeGenModel, GenerationConfig=FakeGenConfig
    )

    class FakeEmbModel:
        @classmethod
        def from_pretrained(cls, model):
            return cls()

        def get_embeddings(self, batch):
            vals = embed_values if embed_values is not None else [0.1, 0.2, 0.3]
            return [types.SimpleNamespace(values=vals) for _ in batch]

    langmod = _mod("vertexai.language_models", TextEmbeddingModel=FakeEmbModel)
    vertexai = _mod("vertexai", generative_models=genmod, language_models=langmod)
    _install(monkeypatch, "vertexai", vertexai)
    _install(monkeypatch, "vertexai.generative_models", genmod)
    _install(monkeypatch, "vertexai.language_models", langmod)


class TestVertexProvider:
    def test_generate_with_messages(self, monkeypatch):
        _install_vertex(monkeypatch, generate_text="GEMINI")
        assert (
            VertexLLMProvider(project="proj").generate_with_messages(
                [{"role": "user", "content": "hi"}]
            )
            == "GEMINI"
        )

    def test_system_instruction_path(self, monkeypatch):
        _install_vertex(monkeypatch, generate_text="SYS")
        out = VertexLLMProvider(project="proj").generate_with_messages(
            [{"role": "system", "content": "be terse"}, {"role": "user", "content": "hi"}]
        )
        assert out == "SYS"

    def test_embed_documents(self, monkeypatch):
        _install_vertex(monkeypatch, embed_values=[0.5, 0.6])
        out = VertexEmbeddingProvider(project="proj").embed_documents(["a", "b"])
        assert out == [[0.5, 0.6], [0.5, 0.6]]

    def test_missing_project_raises(self, monkeypatch):
        monkeypatch.setattr(Config, "GOOGLE_CLOUD_PROJECT", "")
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT required"):
            VertexLLMProvider()


# --------------------------------------------------------------------------- #
# Provider ABC contract (audit 009 #8) — the guarantees the policy gate relies on.
# --------------------------------------------------------------------------- #
CONTRACT_CASES = [
    ("ollama-llm", lambda: OllamaLLMProvider(), True),
    ("ollama-embed", lambda: OllamaEmbeddingProvider(), True),
    ("anthropic", lambda: AnthropicLLMProvider(api_key="sk-ant-x"), False),
    ("openai-llm", lambda: OpenAILLMProvider(api_key="sk-x"), False),
    ("openai-embed", lambda: OpenAIEmbeddingProvider(api_key="sk-x"), False),
    ("vertex-llm", lambda: VertexLLMProvider(project="p"), False),
    ("vertex-embed", lambda: VertexEmbeddingProvider(project="p"), False),
    (
        "openai-compat",
        lambda: OpenAICompatibleLLMProvider(base_url="http://x/v1", model="m", is_local=False),
        False,
    ),
]
_IDS = [c[0] for c in CONTRACT_CASES]


@pytest.mark.parametrize("label,factory,expected_local", CONTRACT_CASES, ids=_IDS)
def test_provider_locality_contract(label, factory, expected_local):
    """get_privacy_profile().is_local and the is_local property must agree and be
    correct — PolicyEngine.guard reads exactly this to decide local vs. cloud."""
    p = factory()
    assert p.get_privacy_profile().is_local is expected_local
    assert p.is_local is expected_local
    assert isinstance(p, (LLMProvider, EmbeddingProvider))


@pytest.mark.parametrize("label,factory,expected_local", CONTRACT_CASES, ids=_IDS)
def test_provider_health_check_never_raises(label, factory, expected_local, monkeypatch):
    """health_check() must swallow a raising is_available() and report unavailable
    — never propagate. The policy gate calls it defensively."""
    p = factory()
    monkeypatch.setattr(p, "is_available", _raise)
    health = p.health_check()
    assert isinstance(health, ProviderHealth)
    assert health.available is False
    assert "error" in health.detail.lower()
