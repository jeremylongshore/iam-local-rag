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
from nexus.core.rag_pipeline import RAGPipeline
from nexus.core.router import ProviderRouter
from nexus.retrieval.base import IndexStats, RetrievedChunk, Retriever
from nexus.retrieval.embedding_adapter import ABCEmbeddingAdapter

SECRET_SENTINEL = "AKIAIOSFODNN7EXAMPLE"  # matches the aws_access_key pattern


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
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


class FakeRetriever(Retriever):
    """Returns preset chunks; reports a configurable locality for the gate."""

    name = "fake"

    def __init__(self, chunks, is_local=True, label="ollama"):
        self._chunks = chunks
        self._is_local = is_local
        self._label = label

    def index(self, documents):
        return IndexStats(chunks_indexed=len(documents), backend=self.name)

    def retrieve(self, query, k):
        return self._chunks[:k]

    def exists(self):
        return True

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label=self._label, is_local=self._is_local)


def _chunk(text, source="a.txt", score=0.9):
    return RetrievedChunk(
        content=text,
        source=source,
        score=score,
        chunk_id=RetrievedChunk.hash_content(text)[:12],
        content_hash=RetrievedChunk.hash_content(text),
    )


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CHROMA_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(Config, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    return tmp_path


# --------------------------------------------------------------------------- #
# (a) embed path no longer crashes on non-Ollama providers
# --------------------------------------------------------------------------- #
def test_adapter_routes_through_abc():
    from nexus.core.providers.openai_provider import OpenAIEmbeddingProvider

    embed = OpenAIEmbeddingProvider(api_key="sk-fake")
    assert not hasattr(embed, "_get_embeddings")  # the old bug relied on this

    embed.embed_documents = lambda texts: [[1.0, 2.0] for _ in texts]
    embed.embed_query = lambda text: [1.0, 2.0]
    adapter = ABCEmbeddingAdapter(embed)
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
        retriever=FakeRetriever([_chunk("local content about cats")], is_local=True),
    )
    pipe.policy = PolicyEngine(mode="local")

    resp = pipe.query(QueryRequest(question="what about cats?", workspace_id="ws_local"))
    assert resp.answer == "ANSWER"
    assert resp.privacy_receipt.llm_destination == "local"
    assert resp.privacy_receipt.chars_sent_to_cloud == 0


def test_local_mode_blocks_cloud_provider(tmp_config):
    pipe = RAGPipeline(
        llm_provider=FakeLLM(is_local=False, label="anthropic"),
        embed_provider=FakeEmbed(is_local=True, label="ollama"),
        workspace_id="ws_local2",
        retriever=FakeRetriever([_chunk("content")], is_local=True),
    )
    pipe.policy = PolicyEngine(mode="local")

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
        retriever=FakeRetriever([_chunk(f"deploy config: {SECRET_SENTINEL}", source="secrets.txt")]),
    )
    pipe.policy = PolicyEngine(mode="hybrid")

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
        retriever=FakeRetriever([], is_local=False, label="openai"),
    )
    pipe.policy = PolicyEngine(mode="cloud")
    doc = tmp_config / "leak.txt"
    doc.write_text(f"aws access {SECRET_SENTINEL} committed by mistake")

    with pytest.raises(PolicyViolation):
        pipe.index_documents(IndexRequest(paths=[str(doc)], workspace_id="ws_secret_embed"))
    assert embed.doc_calls == 0  # never embedded the secret-bearing corpus


# --------------------------------------------------------------------------- #
# (d) insufficient-evidence refusal (invariant #3)
# --------------------------------------------------------------------------- #
def test_refuses_when_evidence_below_floor(tmp_config, monkeypatch):
    from nexus.retrieval.citation_verifier import INSUFFICIENT_EVIDENCE_ANSWER

    llm = FakeLLM(is_local=True, label="ollama")
    pipe = RAGPipeline(
        llm_provider=llm,
        embed_provider=FakeEmbed(is_local=True),
        workspace_id="ws_refuse",
        retriever=FakeRetriever([_chunk("weakly related", score=0.1)], is_local=True),
    )
    pipe.policy = PolicyEngine(mode="local")
    pipe.verifier.min_score = 0.5  # floor above the top score

    resp = pipe.query(QueryRequest(question="q", workspace_id="ws_refuse"))
    assert resp.answer == INSUFFICIENT_EVIDENCE_ANSWER
    assert resp.citations == []
    assert llm.calls == 0  # no generation on refusal
    # Invariant #4 holds on the refusal branch too (009 #22): a receipt is still
    # emitted, marked local + policy-passing, with nothing sent to cloud.
    assert resp.privacy_receipt is not None
    assert resp.privacy_receipt.policy_pass is True
    assert resp.privacy_receipt.chars_sent_to_cloud == 0


def test_cites_when_evidence_above_floor(tmp_config):
    """The SUCCESS half of invariant #3 (audit 009 #5): when retrieval clears the
    evidence floor, the pipeline generates AND returns non-empty, source-attributed
    citations — not just the refusal branch. This runs in the blocking unit gate
    (the equivalent live assertion previously existed only in the non-blocking
    integration suite)."""
    llm = FakeLLM(is_local=True, label="ollama")
    pipe = RAGPipeline(
        llm_provider=llm,
        embed_provider=FakeEmbed(is_local=True),
        workspace_id="ws_cite",
        retriever=FakeRetriever(
            [_chunk("cats are small carnivorous mammals", source="a.txt", score=0.9)],
            is_local=True,
        ),
    )
    pipe.policy = PolicyEngine(mode="local")
    pipe.verifier.min_score = 0.5  # top score 0.9 clears the floor

    resp = pipe.query(QueryRequest(question="what are cats?", workspace_id="ws_cite"))
    assert resp.answer == "ANSWER"  # generated, not the refusal sentinel
    assert resp.citations, "success path must return at least one citation"
    assert resp.citations[0].source == "a.txt"
    assert resp.citations[0].content_hash  # provenance carried through
    assert llm.calls == 1  # the LLM was actually invoked exactly once


# --------------------------------------------------------------------------- #
# (e) provider fallback
# --------------------------------------------------------------------------- #
def test_fallback_skips_erroring_preferred(monkeypatch):
    def fake_get(provider_name=None, mode=None):
        if provider_name == "anthropic":
            raise ValueError("no key configured")
        return FakeLLM(is_local=True, label=provider_name, available=True)

    monkeypatch.setattr(ProviderRouter, "get_llm_provider", staticmethod(fake_get))
    provider = ProviderRouter.get_llm_with_fallback(preferred="anthropic", fallbacks=[], mode="hybrid")
    assert provider.get_privacy_profile().provider_label == "ollama"  # local emergency


# --------------------------------------------------------------------------- #
# (f) workspace_id path-traversal guard
# --------------------------------------------------------------------------- #
def test_workspace_id_rejects_path_traversal():
    from nexus.core.rag_pipeline import _safe_workspace_id

    for bad in ["../evil", "a/b", "..", "", "foo/../bar", "/abs", ".", "a\\b"]:
        with pytest.raises(ValueError):
            _safe_workspace_id(bad)
    assert _safe_workspace_id("default") == "default"
    assert _safe_workspace_id("ws-1_2.x") == "ws-1_2.x"


def test_pipeline_rejects_traversal_workspace(tmp_config):
    with pytest.raises(ValueError):
        RAGPipeline(
            llm_provider=FakeLLM(is_local=True),
            embed_provider=FakeEmbed(is_local=True),
            workspace_id="../escape",
            retriever=FakeRetriever([_chunk("x")]),
        )


def test_fallback_skips_unavailable_preferred(monkeypatch):
    def fake_get(provider_name=None, mode=None):
        available = provider_name != "openai"  # openai reports unavailable
        return FakeLLM(is_local=False, label=provider_name, available=available)

    monkeypatch.setattr(ProviderRouter, "get_llm_provider", staticmethod(fake_get))
    provider = ProviderRouter.get_llm_with_fallback(
        preferred="openai", fallbacks=["anthropic"], mode="cloud"
    )
    assert provider.get_privacy_profile().provider_label == "anthropic"


# --------------------------------------------------------------------------- #
# (g) ingestion loader branches (009 #24) — PDF + unsupported-extension skip
# --------------------------------------------------------------------------- #
def _ingest_pipeline(tmp_config):
    pipe = RAGPipeline(
        llm_provider=FakeLLM(is_local=True),
        embed_provider=FakeEmbed(is_local=True),
        workspace_id="ws_ingest",
        retriever=FakeRetriever([], is_local=True),
    )
    pipe.policy = PolicyEngine(mode="local")
    return pipe


def test_index_pdf_exercises_pypdf_loader(tmp_config):
    from pypdf import PdfWriter

    pdf_path = tmp_config / "doc.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    pipe = _ingest_pipeline(tmp_config)
    result = pipe.index_documents(IndexRequest(paths=[str(pdf_path)], workspace_id="ws_ingest"))

    # The .pdf branch (PyPDFLoader) ran without error and recorded the source —
    # previously only .txt/.md were ever loaded in a test.
    assert any(s.file_path == str(pdf_path) for s in result.document_sources)


def test_index_unsupported_extension_is_skipped(tmp_config):
    bad = tmp_config / "notes.xyz"
    bad.write_text("content that must not be indexed")

    pipe = _ingest_pipeline(tmp_config)
    result = pipe.index_documents(IndexRequest(paths=[str(bad)], workspace_id="ws_ingest"))

    # Unsupported extension hits the `continue` branch: no source, no chunks.
    assert result.document_sources == []
    assert result.total_chunks == 0
