"""
GroundednessMetric — is each generated answer supported by its own citations?

Offline metric (deterministic fakes, no live model). For every non-refusal,
non-secret case it runs the real pipeline, then scores the answer against the
excerpts of the citations the pipeline actually attached, using the shared
GroundednessVerifier heuristic. The aggregate score is the mean per-case
groundedness; a case whose pipeline query raises is skipped (not counted).
"""
from __future__ import annotations

from typing import List

from ...core.models import QueryRequest
from ..base import EvalCase, MetricResult
from ..fakes import build_eval_pipeline
from ..groundedness import GroundednessVerifier


class GroundednessMetric:
    name = "groundedness"
    threshold = 0.6
    requires_live_model = False

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        verifier = GroundednessVerifier()
        applicable = [
            c for c in cases if not c.should_refuse and c.secret_sentinel is None
        ]

        per_case: List[dict] = []
        scores: List[float] = []
        for case in applicable:
            pipe = build_eval_pipeline(case, mode="local")
            try:
                response = pipe.query(
                    QueryRequest(
                        question=case.question,
                        workspace_id="eval",
                        max_results=3,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - a pipeline that can't answer is UNGROUNDED
                scores.append(0.0)
                per_case.append({"id": case.id, "score": 0.0, "error": str(exc)})
                continue

            score = verifier.score(
                response.answer, [c.excerpt for c in response.citations]
            )
            scores.append(score)
            per_case.append({"id": case.id, "score": round(score, 4)})

        if not applicable:
            # Genuinely nothing to evaluate (vs. everything errored, handled above).
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no applicable cases",
                n=0,
                per_case=per_case,
            )

        mean = sum(scores) / len(scores)
        return MetricResult(
            name=self.name,
            score=mean,
            passed=mean >= self.threshold,
            detail=f"mean answer-vs-citation groundedness over {len(scores)} case(s)",
            n=len(scores),
            per_case=per_case,
        )
