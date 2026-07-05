"""
RefusalCorrectness metric (offline, full-pipeline).

Runs each applicable eval case through a real RAGPipeline (wired with the case's
own corpus + a scripted FakeLLM) whose evidence floor is raised to 0.15 so
weak-overlap cases fall through to a code-enforced refusal. A case is classified
correctly when:

  * should_refuse cases return exactly INSUFFICIENT_EVIDENCE_ANSWER, and
  * non-refuse factual cases (relevant docs present) do NOT refuse.

secret_sentinel and prompt-injection cases are out of scope for this metric and
are skipped. The aggregate score is the fraction of applicable cases classified
correctly. The pipeline ledger is swapped for a no-op so the eval never touches
the real SQLite ledger DB.
"""
from __future__ import annotations

from typing import List

from ...core.models import QueryRequest
from ...retrieval.citation_verifier import INSUFFICIENT_EVIDENCE_ANSWER
from ..base import EvalCase, MetricResult
from ..fakes import build_eval_pipeline

_MIN_SCORE = 0.15


class _NoopLedger:
    """Drop-in ledger that records nothing (keeps evals off the real DB)."""

    def record_query_run(self, *args, **kwargs) -> None:  # noqa: D401
        return None

    def record_index_run(self, *args, **kwargs) -> None:
        return None


def _in_scope(case: EvalCase) -> bool:
    """Refusal cases and plain factual cases; skip secret/injection cases."""
    if case.secret_sentinel is not None or case.injection_marker is not None:
        return False
    return case.should_refuse or bool(case.relevant_sources)


class RefusalCorrectness:
    name = "refusal_correctness"
    threshold = 0.9
    requires_live_model = False

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        applicable = [c for c in cases if _in_scope(c)]
        if not applicable:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no refusal-relevant cases",
                n=0,
            )

        per_case: List[dict] = []
        correct = 0
        for case in applicable:
            pipe = build_eval_pipeline(case, min_retrieval_score=_MIN_SCORE)
            pipe.ledger = _NoopLedger()
            try:
                answer = pipe.query(
                    QueryRequest(
                        question=case.question,
                        workspace_id="eval",
                        max_results=3,
                    )
                ).answer
                refused = answer == INSUFFICIENT_EVIDENCE_ANSWER
                error = ""
            except Exception as exc:  # noqa: BLE001 — a crash is a failed classification
                refused = False
                error = type(exc).__name__

            expect_refuse = case.should_refuse
            ok = not error and refused == expect_refuse
            if ok:
                correct += 1
            per_case.append(
                {
                    "id": case.id,
                    "expected_refusal": expect_refuse,
                    "refused": refused,
                    "correct": ok,
                    "error": error,
                }
            )

        score = correct / len(applicable)
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            detail=f"{correct}/{len(applicable)} cases classified correctly",
            n=len(applicable),
            per_case=per_case,
        )
