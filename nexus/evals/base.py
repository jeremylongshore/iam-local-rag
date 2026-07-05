"""
Evaluation harness base types.

Deterministic, offline-first: an EvalCase carries its own corpus + expectations,
and metrics observe the pipeline's behavior through controllable fakes (see
fakes.py) so the core metric suite runs in the unit gate with no Ollama. Metrics
that genuinely need a live model declare `requires_live_model = True`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable


@dataclass
class Doc:
    """One document in an eval case's corpus."""

    source: str
    text: str
    is_relevant: bool = False  # ground-truth relevance for recall/citation metrics


@dataclass
class EvalCase:
    """A single evaluation scenario, self-contained and deterministic."""

    id: str
    question: str
    docs: List[Doc] = field(default_factory=list)
    must_contain: List[str] = field(default_factory=list)  # answer should contain these
    should_refuse: bool = False  # retrieval should be judged insufficient
    injection_marker: Optional[str] = None  # if the answer contains this, injection won
    secret_sentinel: Optional[str] = None  # a planted secret that must be blocked
    scripted_answer: Optional[str] = None  # what the fake LLM returns (deterministic)

    @property
    def relevant_sources(self) -> List[str]:
        return [d.source for d in self.docs if d.is_relevant]


@dataclass
class MetricResult:
    """Outcome of running one metric over a set of cases."""

    name: str
    score: float  # 0..1, higher is better
    passed: bool  # score met the metric's threshold
    detail: str = ""
    n: int = 0  # cases evaluated
    per_case: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 4),
            "passed": self.passed,
            "n": self.n,
            "detail": self.detail,
        }


@runtime_checkable
class Metric(Protocol):
    """A metric evaluates a list of EvalCases into one MetricResult."""

    name: str
    #: threshold the aggregate score must meet to pass
    threshold: float
    #: True if the metric needs a live model (Ollama) rather than the deterministic fakes
    requires_live_model: bool

    def evaluate(self, cases: List[EvalCase]) -> MetricResult: ...
