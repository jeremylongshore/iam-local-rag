"""
Unit tests for the nexus.retrieval package: Chroma real scores, the citation
verifier's refusal logic, the qmd JSON parser + availability, and the factory
fallback.
"""
import pytest
from langchain_core.documents import Document

from nexus.core.providers.profiles import ProviderPrivacyProfile
from nexus.retrieval.base import RetrievedChunk
from nexus.retrieval.chroma_retriever import ChromaRetriever
from nexus.retrieval.citation_verifier import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    CitationVerifier,
)
from nexus.retrieval.factory import get_retriever
from nexus.retrieval.qmd_retriever import QmdRetriever, QmdUnavailable


class _KeywordEmbed:
    """Deterministic toy embeddings so Chroma ranks by keyword overlap."""

    _VOCAB = ["cat", "dog", "paris", "tower", "france"]

    def _vec(self, text):
        t = text.lower()
        return [1.0 if w in t else 0.0 for w in self._VOCAB] or [0.0]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)

    def get_embedding_dimension(self):
        return len(self._VOCAB)

    def is_available(self):
        return True

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label="toy", is_local=True)


# --------------------------------------------------------------------------- #
# ChromaRetriever
# --------------------------------------------------------------------------- #
def test_chroma_retriever_real_scores(tmp_path):
    retr = ChromaRetriever(_KeywordEmbed(), str(tmp_path / "chroma"))
    docs = [
        Document(page_content="The Eiffel tower is in paris france", metadata={"source": "a.txt"}),
        Document(page_content="A cat chased a dog", metadata={"source": "b.txt"}),
    ]
    stats = retr.index(docs)
    assert stats.chunks_indexed == 2

    hits = retr.retrieve("tower in paris", k=2)
    assert hits, "expected retrieved chunks"
    assert all(isinstance(h, RetrievedChunk) for h in hits)
    # Real scores are populated and ordered (best first).
    assert hits[0].source == "a.txt"
    assert hits[0].score >= hits[-1].score
    assert hits[0].content_hash and hits[0].chunk_id


def test_chroma_retriever_locality_follows_embed_provider(tmp_path):
    retr = ChromaRetriever(_KeywordEmbed(), str(tmp_path / "chroma"))
    assert retr.get_privacy_profile().is_local is True


# --------------------------------------------------------------------------- #
# CitationVerifier
# --------------------------------------------------------------------------- #
def _chunk(score):
    return RetrievedChunk(content="x", source="s", score=score, chunk_id="c", content_hash="h")


def test_verifier_empty_is_insufficient():
    v = CitationVerifier(min_score=0.0)
    verdict = v.verify([])
    assert verdict.sufficient is False


def test_verifier_below_floor_is_insufficient():
    v = CitationVerifier(min_score=0.5)
    verdict = v.verify([_chunk(0.2), _chunk(0.1)])
    assert verdict.sufficient is False
    assert "below floor" in verdict.reason


def test_verifier_above_floor_is_sufficient():
    v = CitationVerifier(min_score=0.5)
    verdict = v.verify([_chunk(0.9), _chunk(0.1)])
    assert verdict.sufficient is True
    assert verdict.kept == 2


def test_verifier_zero_floor_accepts_any_nonempty():
    v = CitationVerifier(min_score=0.0)
    assert v.verify([_chunk(0.01)]).sufficient is True


def test_refusal_answer_constant():
    assert "Insufficient evidence" in INSUFFICIENT_EVIDENCE_ANSWER


# --------------------------------------------------------------------------- #
# QmdRetriever — JSON parsing + availability (no real qmd needed)
# --------------------------------------------------------------------------- #
def test_qmd_parse_array():
    data = QmdRetriever._parse_query_json('[{"path": "x.md", "score": 0.9, "content": "hi"}]')
    assert data[0]["score"] == 0.9


def test_qmd_parse_results_object():
    data = QmdRetriever._parse_query_json('{"results": [{"path": "x.md", "score": 0.5}]}')
    assert data[0]["path"] == "x.md"


def test_qmd_parse_ignores_leading_noise():
    noisy = 'Expanding query...\nsome banner\n[{"path": "x.md", "score": 0.7}]'
    data = QmdRetriever._parse_query_json(noisy)
    assert data[0]["score"] == 0.7


def test_qmd_parse_empty():
    assert QmdRetriever._parse_query_json("") == []
    assert QmdRetriever._parse_query_json("not json at all") == []


def test_qmd_unavailable_raises(tmp_path):
    with pytest.raises(QmdUnavailable):
        QmdRetriever(str(tmp_path), qmd_bin="definitely-not-a-real-binary-xyz")


# --------------------------------------------------------------------------- #
# Factory fallback
# --------------------------------------------------------------------------- #
def test_factory_defaults_to_chroma(tmp_path):
    r = get_retriever(_KeywordEmbed(), str(tmp_path / "chroma"), backend="chroma")
    assert isinstance(r, ChromaRetriever)


def test_factory_qmd_missing_falls_back_to_chroma(tmp_path):
    r = get_retriever(
        _KeywordEmbed(), str(tmp_path / "chroma"), backend="qmd", qmd_bin="no-such-qmd-binary"
    )
    assert isinstance(r, ChromaRetriever)  # graceful fallback
