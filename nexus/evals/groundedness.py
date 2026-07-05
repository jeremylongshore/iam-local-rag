"""
Groundedness verifier (P4b) — is the answer supported by the retrieved context?

v1 heuristic: the fraction of the answer's content tokens (stopwords removed)
that appear in the joined context. Reusable both as an eval metric and as a
pre-final-answer check in the pipeline. A learned/NLI verifier is a roadmap item.
"""
from __future__ import annotations

import re
from typing import List

_WORD = re.compile(r"[a-z0-9]+")

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "and",
    "or", "for", "with", "as", "at", "by", "it", "its", "this", "that", "these",
    "those", "be", "been", "has", "have", "had", "not", "no", "yes", "you", "your",
    "we", "our", "i", "he", "she", "they", "them", "from", "about", "into", "than",
    "then", "so", "if", "but", "which", "who", "what", "when", "where", "how", "can",
}


def _content_tokens(text: str) -> set:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 1}


class GroundednessVerifier:
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    def score(self, answer: str, context_texts: List[str]) -> float:
        atoks = _content_tokens(answer)
        if not atoks:
            return 1.0  # empty / refusal answer makes no unsupported claims
        ctoks: set = set()
        for t in context_texts:
            ctoks |= _content_tokens(t)
        covered = sum(1 for w in atoks if w in ctoks)
        return covered / len(atoks)

    def is_grounded(self, answer: str, context_texts: List[str]) -> bool:
        return self.score(answer, context_texts) >= self.threshold
