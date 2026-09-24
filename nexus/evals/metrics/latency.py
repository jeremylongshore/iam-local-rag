"""
Latency (LIVE, informational) — how long does a real Ollama-backed query take?

For a couple of plain factual cases we run the full RAG pipeline against a REAL
Ollama LLM and measure wall-clock query latency in milliseconds. This is a
health/observability signal, not a gate: the score is always 1.0 and the metric
always passes (threshold 1.0), reporting the mean latency in `detail`. It needs a
live model, so it is skipped in the offline gate. Cases whose query raises (e.g.
Ollama unreachable) yield no sample and are skipped.
"""
from __future__ import annotations

import time
from typing import List

from ...core.models import QueryRequest
from ...core.policy import PolicyEngine
from ...core.providers.ollama_provider import OllamaLLMProvider
from ...core.rag_pipeline import RAGPipeline
from ..base import EvalCase, MetricResult
from ..fakes import FakeEmbed, KeywordRetriever

# Keep the live probe cheap — a couple of factual samples is enough for a signal.
_MAX_SAMPLES = 2


class Latency:
    """Mean wall-clock query latency (ms) over a few factual cases. Informational."""

    name = "latency"
    threshold = 1.0  # informational: score is always 1.0, so it always passes
    requires_live_model = True

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        # Plain factual cases only: no refusal, no planted secret, no injection.
        applicable = [
            c
            for c in cases
            if not c.should_refuse
            and c.secret_sentinel is None
            and c.injection_marker is None
        ][:_MAX_SAMPLES]

        latencies_ms: List[float] = []
        per_case: List[dict] = []
        for case in applicable:
            try:
                pipe = RAGPipeline(
                    llm_provider=OllamaLLMProvider(),
                    embed_provider=FakeEmbed(),
                    workspace_id="eval",
                    retriever=KeywordRetriever(case.docs),
                )
                pipe.policy = PolicyEngine(mode="local")
                start = time.time()
                pipe.query(
                    QueryRequest(question=case.question, workspace_id="eval", max_results=3)
                )
                elapsed_ms = (time.time() - start) * 1000.0
            except Exception:  # noqa: BLE001 - no live model / transport error → no sample
                per_case.append({"id": case.id, "skipped": True})
                continue

            latencies_ms.append(elapsed_ms)
            per_case.append({"id": case.id, "latency_ms": round(elapsed_ms, 1)})

        if not latencies_ms:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no live latency samples (skipped)",
                n=0,
                per_case=per_case,
            )

        mean_ms = sum(latencies_ms) / len(latencies_ms)
        return MetricResult(
            name=self.name,
            score=1.0,
            passed=True,
            detail=f"mean {round(mean_ms)}ms over {len(latencies_ms)} case(s)",
            n=len(latencies_ms),
            per_case=per_case,
        )
