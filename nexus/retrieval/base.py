"""
Retrieval stage interface.

A `Retriever` indexes document chunks and answers queries with scored,
attributed `RetrievedChunk`s. Backends (Chroma, qmd) implement this so the
pipeline is agnostic to how retrieval happens.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from ..core.providers.profiles import ProviderPrivacyProfile


@dataclass
class RetrievedChunk:
    """A retrieved chunk with a real relevance score and full provenance."""

    content: str
    source: str
    score: float  # higher = more relevant; normalized to 0..1 where the backend allows
    chunk_id: str
    content_hash: str
    retrieval_kind: str = "dense"  # "dense" | "hybrid" | "bm25"
    page: Optional[int] = None
    rerank_score: Optional[float] = None

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class IndexStats:
    chunks_indexed: int = 0
    backend: str = ""
    detail: str = ""


class Retriever(ABC):
    """Abstract retrieval backend."""

    #: short label for receipts / logs
    name: str = "retriever"

    @abstractmethod
    def index(self, documents: List) -> IndexStats:
        """Index a list of LangChain Document chunks. Returns stats."""

    @abstractmethod
    def retrieve(self, query: str, k: int) -> List[RetrievedChunk]:
        """Return up to k scored chunks, most relevant first."""

    @abstractmethod
    def exists(self) -> bool:
        """True if this retriever has an index ready to query."""

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        """
        Locality of the retrieval/embedding path, so the PolicyEngine can gate
        it uniformly. Default is local; ChromaRetriever delegates to its embed
        provider (which may be cloud).
        """
        return ProviderPrivacyProfile(provider_label=self.name, is_local=True)

    def is_local(self) -> bool:
        return self.get_privacy_profile().is_local
