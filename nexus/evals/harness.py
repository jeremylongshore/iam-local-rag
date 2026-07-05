"""
Eval harness runner — runs a set of metrics over a set of cases and reports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base import EvalCase, Metric, MetricResult


@dataclass
class EvalReport:
    results: List[MetricResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "metrics": [r.as_dict() for r in self.results],
        }

    def render(self) -> str:
        lines = ["NEXUS eval report", "=" * 60]
        width = max((len(r.name) for r in self.results), default=10)
        for r in self.results:
            mark = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{mark}] {r.name:<{width}}  score={r.score:.3f}  n={r.n}  {r.detail}")
        lines.append("=" * 60)
        lines.append(f"OVERALL: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


class EvalHarness:
    def __init__(self, cases: List[EvalCase]):
        self.cases = cases

    def run(self, metrics: List[Metric], include_live: bool = False) -> EvalReport:
        results: List[MetricResult] = []
        for metric in metrics:
            if getattr(metric, "requires_live_model", False) and not include_live:
                continue
            results.append(metric.evaluate(self.cases))
        return EvalReport(results)
