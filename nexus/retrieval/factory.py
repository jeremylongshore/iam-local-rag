"""Retriever factory — pick a backend from config, fail-soft to Chroma."""
from __future__ import annotations

import logging
import os
from typing import Optional

from ..core.config import Config
from ..core.providers.base import EmbeddingProvider
from .base import Retriever
from .chroma_retriever import ChromaRetriever

logger = logging.getLogger("nexus.retrieval")


def get_retriever(
    embed_provider: EmbeddingProvider,
    chroma_path: str,
    workspace_dir: Optional[str] = None,
    backend: Optional[str] = None,
    qmd_bin: Optional[str] = None,
) -> Retriever:
    backend = (backend or Config.NEXUS_RETRIEVER).lower()

    if backend == "qmd":
        from .qmd_retriever import QmdRetriever, QmdUnavailable

        try:
            return QmdRetriever(
                workspace_dir=workspace_dir or os.path.dirname(chroma_path) or chroma_path,
                qmd_bin=qmd_bin or Config.QMD_BIN,
            )
        except QmdUnavailable as e:
            logger.warning("qmd backend unavailable (%s); falling back to Chroma", e)

    return ChromaRetriever(embed_provider, chroma_path)
