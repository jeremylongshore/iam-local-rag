"""
Retrieval backends for NEXUS.

`Retriever` is the stage interface; `ChromaRetriever` is the zero-dependency
default (dense vectors with real relevance scores), and `QmdRetriever` drives
the homegrown qmd hybrid (BM25 + vector + rerank) engine via its CLI. Pick a
backend with `get_retriever()` (config-driven, qmd falls back to Chroma if the
binary is missing).
"""
from .base import RetrievedChunk, Retriever
from .citation_verifier import CitationVerifier, EvidenceVerdict
from .factory import get_retriever

__all__ = [
    "RetrievedChunk",
    "Retriever",
    "CitationVerifier",
    "EvidenceVerdict",
    "get_retriever",
]
