"""
LangChain Embeddings adapter over the NEXUS provider ABC.

Lets Chroma (and any LangChain vector store) consume ANY EmbeddingProvider —
ollama, openai, vertex — through the same embed_documents / embed_query surface.
This is the fix for the original crash that called the Ollama-only private
`_get_embeddings()` on providers that never defined it.
"""
from __future__ import annotations

from typing import List

from langchain_core.embeddings import Embeddings as LCEmbeddings

from ..core.providers.base import EmbeddingProvider


class ABCEmbeddingAdapter(LCEmbeddings):
    def __init__(self, provider: EmbeddingProvider):
        self._provider = provider

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._provider.embed_documents(list(texts))

    def embed_query(self, text: str) -> List[float]:
        return self._provider.embed_query(text)
