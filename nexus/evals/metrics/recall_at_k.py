"""
Recall@k metric (offline, retrieval-only).

For every eval case that declares ground-truth relevant docs (is_relevant=True),
run the deterministic KeywordRetriever over the case's own corpus and measure the
fraction of that case's relevant sources that land in the top-k retrieved sources.
The aggregate score is the mean per-case recall. This exercises only the retrieval
stage — never the full pipeline / LLM / ledger — so it stays fast and offline.
"""
from __future__ import annotations

from typing import List

from ..base import EvalCase, MetricResult
from ..fakes import KeywordRetriever

_K = 3


class RecallAtK:
    name = "recall_at_k"
    threshold = 0.8
    requires_live_model = False

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        applicable = [c for c in cases if c.relevant_sources]
        if not applicable:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no cases with ground-truth relevant docs",
                n=0,
            )

        per_case: List[dict] = []
        recalls: List[float] = []
        for case in applicable:
            relevant = set(case.relevant_sources)
            chunks = KeywordRetriever(case.docs).retrieve(case.question, _K)
            retrieved_top = {chunk.source for chunk in chunks[:_K]}
            hit = len(relevant & retrieved_top)
            recall = hit / len(relevant)
            recalls.append(recall)
            per_case.append(
                {
                    "id": case.id,
                    "recall": round(recall, 4),
                    "relevant": sorted(relevant),
                    "retrieved": sorted(retrieved_top),
                }
            )

        score = sum(recalls) / len(recalls)
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            detail=f"mean recall@{_K} over {len(applicable)} cases",
            n=len(applicable),
            per_case=per_case,
        )
