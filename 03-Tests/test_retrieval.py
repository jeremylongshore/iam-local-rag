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
    # Every score must stay in [0, 1] — the contract the CitationVerifier's
    # evidence floor depends on (000-docs/009 #14). Before the cosine+clamp fix
    # the L2 default emitted a real -1.83 here (with a langchain range warning).
    assert all(0.0 <= h.score <= 1.0 for h in hits), [h.score for h in hits]


def test_chroma_scores_never_negative_even_for_unrelated(tmp_path):
    # A query orthogonal to every doc must not produce a negative relevance score
    # that would corrupt the evidence-floor comparison.
    retr = ChromaRetriever(_KeywordEmbed(), str(tmp_path / "chroma"))
    retr.index(
        [Document(page_content="A cat chased a dog", metadata={"source": "b.txt"})]
    )
    hits = retr.retrieve("paris tower france", k=1)  # zero vocab overlap
    assert hits
    assert 0.0 <= hits[0].score <= 1.0


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


# --------------------------------------------------------------------------- #
# QmdRetriever robustness (mocks _binary_ok + _run — no real qmd needed)
# --------------------------------------------------------------------------- #
import os  # noqa: E402
import subprocess  # noqa: E402


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def qmd(tmp_path, monkeypatch):
    monkeypatch.setattr(QmdRetriever, "_binary_ok", lambda self: True)
    return QmdRetriever(str(tmp_path), qmd_bin="qmd")


def test_qmd_retrieve_raises_on_nonzero_exit(qmd, monkeypatch):
    monkeypatch.setattr(qmd, "_run", lambda args, check=False: _cp(returncode=1, stderr="boom"))
    with pytest.raises(QmdUnavailable):
        qmd.retrieve("q", 3)


def test_qmd_retrieve_uses_end_of_options_sentinel(qmd, monkeypatch):
    captured = {}

    def fake_run(args, check=False):
        captured["args"] = args
        return _cp(0, stdout="[]")

    monkeypatch.setattr(qmd, "_run", fake_run)
    qmd.retrieve("--help", 3)  # a dash-prefixed query must not be parsed as a flag
    assert "--" in captured["args"]
    assert captured["args"].index("--") < captured["args"].index("--help")


def test_qmd_retrieve_backfills_content_from_corpus(qmd, monkeypatch):
    os.makedirs(qmd._corpus, exist_ok=True)
    fname = "abc123.md"
    with open(os.path.join(qmd._corpus, fname), "w") as f:
        f.write("the full chunk body")
    qmd._save_manifest({fname: {"source": "orig.txt", "content_hash": "hh"}})
    monkeypatch.setattr(
        qmd, "_run", lambda args, check=False: _cp(0, stdout=f'[{{"path": "{fname}", "score": 0.8}}]')
    )
    hits = qmd.retrieve("q", 3)
    assert hits and hits[0].content == "the full chunk body"
    assert hits[0].source == "orig.txt"


def test_qmd_retrieve_skips_ungroundable_hit(qmd, monkeypatch):
    os.makedirs(qmd._corpus, exist_ok=True)
    monkeypatch.setattr(
        qmd, "_run", lambda args, check=False: _cp(0, stdout='[{"path": "missing.md", "score": 0.8}]')
    )
    assert qmd.retrieve("q", 3) == []  # no body + no corpus file => dropped, not answered blank


def test_qmd_index_raises_on_embed_failure(qmd, monkeypatch):
    from langchain_core.documents import Document

    def fake_run(args, check=False):
        if args and args[0] == "embed":
            return _cp(returncode=1, stderr="no embed model")
        return _cp(0)

    monkeypatch.setattr(qmd, "_run", fake_run)
    with pytest.raises(QmdUnavailable):
        qmd.index([Document(page_content="x", metadata={"source": "a.txt"})])
