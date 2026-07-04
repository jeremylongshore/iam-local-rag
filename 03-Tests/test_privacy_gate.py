"""
End-to-end privacy-gate tests (acceptance invariants 1, 2, 6).

Proves, at the pipeline level:
  (a) the OpenAI/Vertex embed path no longer crashes (the _get_embeddings bug);
  (b) LOCAL mode makes zero external network calls (network-blocked);
  (c) a sentinel secret in a chunk is blocked before any LLM *or* embedding
      cloud call;
  (d) provider fallback selects the next available provider.

Uses in-process fakes so nothing touches a real network or model.
"""
import socket

import pytest

from nexus.core.config import Config, NexusMode
from nexus.core.models import IndexRequest, QueryRequest
from nexus.core.policy import PolicyEngine, PolicyViolation
from nexus.core.providers.profiles import ProviderPrivacyProfile
from nexus.core.rag_pipeline import RAGPipeline, _ABCEmbeddingAdapter
from nexus.core.router import ProviderRouter

SECRET_SENTINEL = "AKIAIOSFODNN7EXAMPLE"  # matches the aws_access_key pattern


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeDoc:
    def __init__(self, content, metadata=None):
        self.page_content = content
        self.metadata = metadata or {}


class FakeRetriever:
    def __init__(self, docs):
        self._docs = docs

    def invoke(self, query):
        return self._docs


class FakeVectorStore:
    def __init__(self, docs):
        self._docs = docs

    def as_retriever(self, **kwargs):
        return FakeRetriever(self._docs)


class FakeLLM:
    def __init__(self, is_local=False, label="anthropic", available=True):
        self.calls = 0
        self._is_local = is_local
        self._label = label
        self._available = available

    def generate(self, prompt, **kwargs):
        self.calls += 1
        return "ANSWER"

    def generate_with_messages(self, *a, **k):
        self.calls += 1
        return "ANSWER"

    def get_model_name(self):
        return "fake-model"

    def is_available(self):
        return self._available

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label=self._label, is_local=self._is_local)


class FakeEmbed:
    def __init__(self, is_local=True, label="ollama"):
        self.doc_calls = 0
        self.query_calls = 0
        self._is_local = is_local
        self._label = label

    def embed_documents(self, texts):
        self.doc_calls += 1
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, text):
        self.query_calls += 1
        return [0.1, 0.2, 0.3]

    def get_embedding_dimension(self):
        return 3

    def is_available(self):
        return True

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label=self._label, is_local=self._is_local)


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CHROMA_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(Config, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    return tmp_path


# --------------------------------------------------------------------------- #
# (a) embed path no longer crashes on non-Ollama providers
# --------------------------------------------------------------------------- #
def test_adapter_routes_through_abc():
    """The adapter must call the ABC methods, not the Ollama-only private one."""
    from nexus.core.providers.openai_provider import OpenAIEmbeddingProvider

    embed = OpenAIEmbeddingProvider(api_key="sk-fake")
    # The old pipeline called this private method, which OpenAI never defined.
    assert not hasattr(embed, "_get_embeddings")

    embed.embed_documents = lambda texts: [[1.0, 2.0] for _ in texts]
    embed.embed_query = lambda text: [1.0, 2.0]
    adapter = _ABCEmbeddingAdapter(embed)
    assert adapter.embed_documents(["a", "b"]) == [[1.0, 2.0], [1.0, 2.0]]
    assert adapter.embed_query("q") == [1.0, 2.0]


def test_openai_embed_path_indexes_without_attribute_error(tmp_config, monkeypatch):
    from nexus.core.providers.openai_provider import OpenAIEmbeddingProvider

    monkeypatch.setattr(Config, "NEXUS_MODE", NexusMode.CLOUD)  # cloud embeddings allowed
    embed = OpenAIEmbeddingProvider(api_key="sk-fake")
    monkeypatch.setattr(embed, "embed_documents", lambda texts: [[0.1, 0.2, 0.3] for _ in texts])
    monkeypatch.setattr(embed, "embed_query", lambda text: [0.1, 0.2, 0.3])

    pipe = RAGPipeline(llm_provider=FakeLLM(), embed_provider=embed, workspace_id="ws_embed")
    doc = tmp_config / "d.txt"
    doc.write_text("hello world content for indexing")

    result = pipe.index_documents(IndexRequest(paths=[str(doc)], workspace_id="ws_embed"))
    assert result.total_chunks >= 1  # would have raised AttributeError before the fix


# --------------------------------------------------------------------------- #
# (b) LOCAL mode = zero external calls
# --------------------------------------------------------------------------- #
def test_local_mode_makes_zero_network_calls(tmp_config, monkeypatch):
    def _blocked(*a, **k):
        raise AssertionError("network connect attempted in LOCAL mode")

    monkeypatch.setattr(socket.socket, "connect", _blocked)

    pipe = RAGPipeline(
        llm_provider=FakeLLM(is_local=True, label="ollama"),
        embed_provider=FakeEmbed(is_local=True, label="ollama"),
        workspace_id="ws_local",
    )
    pipe.policy = PolicyEngine(mode="local")
    pipe._vectorstore = FakeVectorStore([FakeDoc("local content about cats", {"source": "a.txt"})])

    resp = pipe.query(QueryRequest(question="what about cats?", workspace_id="ws_local"))
    assert resp.answer == "ANSWER"
    assert resp.privacy_receipt.llm_destination == "local"
    assert resp.privacy_receipt.chars_sent_to_cloud == 0


def test_local_mode_blocks_cloud_provider(tmp_config):
    pipe = RAGPipeline(
        llm_provider=FakeLLM(is_local=False, label="anthropic"),
        embed_provider=FakeEmbed(is_local=True, label="ollama"),
        workspace_id="ws_local2",
    )
    pipe.policy = PolicyEngine(mode="local")
    pipe._vectorstore = FakeVectorStore([FakeDoc("content", {"source": "a.txt"})])

    with pytest.raises(PolicyViolation):
        pipe.query(QueryRequest(question="q", workspace_id="ws_local2"))
    assert pipe.llm_provider.calls == 0  # blocked before generation


# --------------------------------------------------------------------------- #
# (c) sentinel secret blocked before any cloud call
# --------------------------------------------------------------------------- #
def test_secret_blocked_before_cloud_llm(tmp_config):
    llm = FakeLLM(is_local=False, label="anthropic")
    pipe = RAGPipeline(
        llm_provider=llm,
        embed_provider=FakeEmbed(is_local=True, label="ollama"),
        workspace_id="ws_secret",
    )
    pipe.policy = PolicyEngine(mode="hybrid")
    pipe._vectorstore = FakeVectorStore(
        [FakeDoc(f"deploy config: {SECRET_SENTINEL}", {"source": "secrets.txt"})]
    )

    with pytest.raises(PolicyViolation):
        pipe.query(QueryRequest(question="what is the config?", workspace_id="ws_secret"))
    assert llm.calls == 0  # never reached the cloud LLM


def test_secret_blocked_before_cloud_embedding(tmp_config, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_MODE", NexusMode.CLOUD)
    embed = FakeEmbed(is_local=False, label="openai")  # cloud embeddings
    pipe = RAGPipeline(
        llm_provider=FakeLLM(is_local=False),
        embed_provider=embed,
        workspace_id="ws_secret_embed",
    )
    pipe.policy = PolicyEngine(mode="cloud")
    doc = tmp_config / "leak.txt"
    doc.write_text(f"aws access {SECRET_SENTINEL} committed by mistake")

    with pytest.raises(PolicyViolation):
        pipe.index_documents(IndexRequest(paths=[str(doc)], workspace_id="ws_secret_embed"))
    assert embed.doc_calls == 0  # never embedded the secret-bearing corpus


# --------------------------------------------------------------------------- #
# (d) provider fallback
# --------------------------------------------------------------------------- #
def test_fallback_skips_erroring_preferred(monkeypatch):
    def fake_get(provider_name=None, mode=None):
        if provider_name == "anthropic":
            raise ValueError("no key configured")
        return FakeLLM(is_local=True, label=provider_name, available=True)

    monkeypatch.setattr(ProviderRouter, "get_llm_provider", staticmethod(fake_get))
    provider = ProviderRouter.get_llm_with_fallback(preferred="anthropic", fallbacks=[], mode="hybrid")
    assert provider.get_privacy_profile().provider_label == "ollama"  # local emergency


def test_fallback_skips_unavailable_preferred(monkeypatch):
    def fake_get(provider_name=None, mode=None):
        available = provider_name != "openai"  # openai reports unavailable
        return FakeLLM(is_local=False, label=provider_name, available=available)

    monkeypatch.setattr(ProviderRouter, "get_llm_provider", staticmethod(fake_get))
    provider = ProviderRouter.get_llm_with_fallback(
        preferred="openai", fallbacks=["anthropic"], mode="cloud"
    )
    assert provider.get_privacy_profile().provider_label == "anthropic"
