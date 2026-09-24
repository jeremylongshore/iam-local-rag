"""
Deterministic, offline fakes for the eval harness.

A KeywordRetriever ranks an EvalCase's own docs by keyword overlap (so recall@k
and citation metrics are meaningful without embeddings), a FakeLLM returns a
scripted answer, and build_eval_pipeline wires them into a real RAGPipeline so
the actual policy gate / citation / refusal paths are exercised.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..core.providers.profiles import ProviderPrivacyProfile
from ..retrieval.base import IndexStats, RetrievedChunk, Retriever
from .base import Doc, EvalCase

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return set(_WORD.findall(text.lower()))


class FakeEmbed:
    """Local embedding stub (never actually used for ranking here)."""

    def embed_documents(self, texts):
        return [[0.0] for _ in texts]

    def embed_query(self, text):
        return [0.0]

    def get_embedding_dimension(self):
        return 1

    def is_available(self):
        return True

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label="fake-embed", is_local=True)


class FakeLLM:
    """Returns a scripted answer (or echoes the retrieved context)."""

    def __init__(self, answer: Optional[str] = None, is_local: bool = True, label: str = "ollama"):
        self._answer = answer
        self._is_local = is_local
        self._label = label
        self.calls = 0
        self.last_prompt: Optional[str] = None

    def generate(self, prompt, **kwargs):
        self.calls += 1
        self.last_prompt = prompt
        if self._answer is not None:
            return self._answer
        return prompt  # echo — lets injection metrics see what reached the model

    def generate_with_messages(self, *a, **k):
        return self.generate("", **k)

    def get_model_name(self):
        return f"fake-{self._label}"

    def is_available(self):
        return True

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label=self._label, is_local=self._is_local)


class KeywordRetriever(Retriever):
    """Ranks the case's docs by keyword overlap with the query. Local."""

    name = "keyword-eval"

    def __init__(self, docs: List[Doc], is_local: bool = True):
        self._docs = docs
        self._is_local = is_local

    def index(self, documents):
        return IndexStats(chunks_indexed=len(documents), backend=self.name)

    def retrieve(self, query: str, k: int) -> List[RetrievedChunk]:
        qtok = _tokens(query)
        scored = []
        for d in self._docs:
            dtok = _tokens(d.text)
            overlap = len(qtok & dtok)
            denom = max(1, len(qtok))
            score = overlap / denom
            scored.append((score, d))
        scored.sort(key=lambda s: s[0], reverse=True)
        out = []
        for score, d in scored[:k]:
            out.append(
                RetrievedChunk(
                    content=d.text,
                    source=d.source,
                    score=float(score),
                    chunk_id=RetrievedChunk.hash_content(d.text)[:12],
                    content_hash=RetrievedChunk.hash_content(d.text),
                    retrieval_kind="bm25",
                )
            )
        return out

    def exists(self):
        return bool(self._docs)

    def get_privacy_profile(self):
        return ProviderPrivacyProfile(provider_label=self.name, is_local=self._is_local)


def build_eval_pipeline(
    case: EvalCase,
    *,
    mode: str = "local",
    llm_is_local: bool = True,
    llm_label: str = "ollama",
    min_retrieval_score: float = 0.0,
):
    """Build a real RAGPipeline wired with the case's docs + a scripted LLM."""
    # Isolate eval runs from the production audit ledger — build the temp ledger
    # FIRST and inject it, so the pipeline never opens the default ./nexus_ledger.db
    # at construction (which it would if we swapped pipe.ledger only afterwards).
    import os
    import tempfile

    from ..core.ledger import RunLedger
    from ..core.policy import PolicyEngine
    from ..core.rag_pipeline import RAGPipeline

    eval_ledger = RunLedger(os.path.join(tempfile.gettempdir(), "nexus_eval_ledger.db"))
    pipe = RAGPipeline(
        llm_provider=FakeLLM(answer=case.scripted_answer, is_local=llm_is_local, label=llm_label),
        embed_provider=FakeEmbed(),
        workspace_id="eval",
        retriever=KeywordRetriever(case.docs, is_local=True),
        ledger=eval_ledger,
    )
    pipe.policy = PolicyEngine(mode=mode)
    pipe.verifier.min_score = min_retrieval_score
    return pipe
