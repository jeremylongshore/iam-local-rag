"""
Citation / evidence verifier (acceptance invariant #3).

Decides, BEFORE generation, whether retrieval returned enough evidence to answer.
If not, the pipeline refuses ("insufficient evidence") instead of letting the LLM
guess — enforced in code, not just requested in the prompt.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .base import RetrievedChunk

INSUFFICIENT_EVIDENCE_ANSWER = "Insufficient evidence in the provided documents to answer."


@dataclass
class EvidenceVerdict:
    sufficient: bool
    reason: str
    top_score: float
    kept: int


class CitationVerifier:
    """Gate retrieval quality behind a minimum-score floor + a non-empty check."""

    def __init__(self, min_score: float = 0.0):
        self.min_score = min_score

    def verify(self, chunks: List[RetrievedChunk]) -> EvidenceVerdict:
        if not chunks:
            return EvidenceVerdict(False, "no chunks retrieved", 0.0, 0)

        top = max(c.score for c in chunks)
        if self.min_score > 0.0 and top < self.min_score:
            return EvidenceVerdict(
                False,
                f"top retrieval score {top:.3f} below floor {self.min_score:.3f}",
                top,
                0,
            )
        return EvidenceVerdict(True, "sufficient", top, len(chunks))
