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

    def _load(self) -> Optional[Chroma]:
        if self._store is None:
            if os.path.exists(self._persist_directory) and os.listdir(self._persist_directory):
                self._store = Chroma(
                    persist_directory=self._persist_directory,
                    embedding_function=self._embeddings(),
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
            chunks.append(
                RetrievedChunk(
                    content=content,
                    source=doc.metadata.get("source", "unknown"),
                    page=doc.metadata.get("page"),
                    score=float(score),
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
