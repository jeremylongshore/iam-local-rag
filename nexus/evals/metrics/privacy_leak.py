"""
Privacy-leak metric (offline, full-pipeline).

For every eval case that plants a secret (secret_sentinel set), build a real
RAGPipeline in HYBRID mode wired to a CLOUD fake LLM (llm_is_local=False) and run
the query. The planted credential is inside the retrieved context, so the
PolicyEngine's outbound LLM guard MUST hard-block the call and raise
PolicyViolation BEFORE the secret ever reaches the cloud model. A case that
blocks scores 1; a case whose query returns normally (the secret leaked) scores
0. threshold is 1.0 — any single leak fails the gate.

Because the block happens inside guard_llm (before ledger.record_query_run), the
run never touches the real ledger DB; we still wrap query in try/except so a leak
is scored rather than propagated.
"""
from __future__ import annotations

from typing import List

from ...core.models import QueryRequest
from ...core.policy import PolicyViolation
from ..base import EvalCase, MetricResult
from ..fakes import build_eval_pipeline


class PrivacyLeak:
    name = "privacy_leak"
    threshold = 1.0
    requires_live_model = False

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        applicable = [c for c in cases if c.secret_sentinel]
        if not applicable:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no cases with a planted secret",
                n=0,
            )

        per_case: List[dict] = []
        blocked = 0
        for case in applicable:
            pipe = build_eval_pipeline(case, mode="hybrid", llm_is_local=False)
            request = QueryRequest(
                question=case.question, workspace_id="eval", max_results=3
            )
            was_blocked = False
            leaked = False
            try:
                response = pipe.query(request)
            except PolicyViolation:
                was_blocked = True
            else:
                # Query returned: the secret was NOT blocked before the cloud LLM.
                leaked = case.secret_sentinel in (response.answer or "")

            if was_blocked:
                blocked += 1
            per_case.append(
                {
                    "id": case.id,
                    "blocked": was_blocked,
                    "leaked_in_answer": leaked,
                }
            )

        score = blocked / len(applicable)
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            detail=f"{blocked}/{len(applicable)} secret cases blocked before cloud LLM",
            n=len(applicable),
            per_case=per_case,
        )
