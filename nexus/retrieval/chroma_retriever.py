"""
Chroma retrieval backend — the zero-dependency default.

Dense vector retrieval with REAL relevance scores (not the old positional
1/(i+1) placeholder), via Chroma's `similarity_search_with_relevance_scores`.
"""
from __future__ import annotations

import os
from typing import List, Optional

from langchain_chroma import Chroma

from ..core.providers.base import EmbeddingProvider
from ..core.providers.profiles import ProviderPrivacyProfile
from .base import IndexStats, RetrievedChunk, Retriever
from .embedding_adapter import ABCEmbeddingAdapter


class ChromaRetriever(Retriever):
    name = "chroma"

    def __init__(self, embed_provider: EmbeddingProvider, persist_directory: str):
        self._embed_provider = embed_provider
        self._persist_directory = persist_directory
        self._store: Optional[Chroma] = None
        self._adapter: Optional[ABCEmbeddingAdapter] = None

    def _embeddings(self) -> ABCEmbeddingAdapter:
        if self._adapter is None:
            self._adapter = ABCEmbeddingAdapter(self._embed_provider)
        return self._adapter

    # Cosine space keeps relevance in a sane range for text embeddings. Chroma's
    # DEFAULT is L2, whose langchain relevance function (1 - dist/sqrt(2)) goes
    # NEGATIVE for distant chunks — the CitationVerifier's evidence floor assumes
    # [0, 1], so an out-of-range score silently distorts the refusal decision
    # (000-docs/009 #14). Set cosine on new collections; the retrieve() clamp is
    # the belt-and-suspenders guarantee for any existing L2 index.
    _COLLECTION_METADATA = {"hnsw:space": "cosine"}

    def _load(self) -> Optional[Chroma]:
        if self._store is None:
            if os.path.exists(self._persist_directory) and os.listdir(self._persist_directory):
                self._store = Chroma(
                    persist_directory=self._persist_directory,
                    embedding_function=self._embeddings(),
                    collection_metadata=self._COLLECTION_METADATA,
                )
        return self._store

    def index(self, documents: List) -> IndexStats:
        if self._store is None and not (
            os.path.exists(self._persist_directory) and os.listdir(self._persist_directory)
        ):
            self._store = Chroma.from_documents(
                documents=documents,
                embedding=self._embeddings(),
                persist_directory=self._persist_directory,
                collection_metadata=self._COLLECTION_METADATA,
            )
        else:
            store = self._load()
            store.add_documents(documents)
        return IndexStats(chunks_indexed=len(documents), backend=self.name)

    def retrieve(self, query: str, k: int) -> List[RetrievedChunk]:
        store = self._load()
        if store is None:
            return []
        results = store.similarity_search_with_relevance_scores(query, k=k)
        chunks: List[RetrievedChunk] = []
        for doc, score in results:
            content = doc.page_content
            # Clamp to the [0, 1] contract the CitationVerifier floor relies on:
            # langchain relevance functions can emit slightly-negative / >1 values.
            clamped = max(0.0, min(1.0, float(score)))
            chunks.append(
                RetrievedChunk(
                    content=content,
                    source=doc.metadata.get("source", "unknown"),
                    page=doc.metadata.get("page"),
                    score=clamped,
                    chunk_id=RetrievedChunk.hash_content(content)[:12],
                    content_hash=RetrievedChunk.hash_content(content),
                    retrieval_kind="dense",
                )
            )
        return chunks

    def exists(self) -> bool:
        return self._load() is not None

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        # Chroma embeds via the NEXUS embed provider, so retrieval locality
        # follows that provider (cloud embed provider => not local).
        return self._embed_provider.get_privacy_profile()
