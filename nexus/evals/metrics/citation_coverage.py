"""
CitationCoverage metric (offline).

For each case that has ground-truth relevant docs and is expected to answer
(not a refusal case, not a planted-secret case), run the real pipeline and
measure the fraction of the case's relevant sources that appear among the
returned citations' `source` fields. The metric score is the mean coverage
across applicable cases. A query that raises is scored as zero coverage for
that case (a failure to answer cites nothing).
"""
from __future__ import annotations

from typing import List

from ..base import EvalCase, MetricResult
from ..fakes import build_eval_pipeline


class CitationCoverage:
    name = "citation-coverage"
    threshold = 0.8
    requires_live_model = False

    def _applicable(self, case: EvalCase) -> bool:
        if case.should_refuse or case.secret_sentinel:
            return False
        return bool(case.relevant_sources)

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        from ...core.models import QueryRequest

        applicable = [c for c in cases if self._applicable(c)]
        if not applicable:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no cases with relevant docs to cite",
                n=0,
            )

        per_case: List[dict] = []
        total = 0.0
        for case in applicable:
            expected = set(case.relevant_sources)
            try:
                pipe = build_eval_pipeline(case)
                resp = pipe.query(
                    QueryRequest(question=case.question, workspace_id="eval", max_results=3)
                )
                cited = {c.source for c in resp.citations}
                covered = len(expected & cited)
                coverage = covered / len(expected)
            except Exception as exc:  # noqa: BLE001 - a failed query cites nothing
                coverage = 0.0
                per_case.append({"id": case.id, "coverage": 0.0, "error": str(exc)})
            else:
                per_case.append(
                    {"id": case.id, "coverage": round(coverage, 4), "cited": sorted(cited)}
                )
            total += coverage

        score = total / len(applicable)
        return MetricResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            detail=f"mean relevant-source citation coverage over {len(applicable)} cases",
            n=len(applicable),
            per_case=per_case,
        )
