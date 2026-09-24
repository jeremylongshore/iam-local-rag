"""
NEXUS evaluation harness.

Deterministic, offline-first metrics over a golden dataset. `default_metrics()`
returns the full suite; the offline subset runs in the unit gate, the live subset
(needs Ollama) runs with `include_live=True`.
"""
from .base import Doc, EvalCase, Metric, MetricResult
from .dataset import GOLDEN_CASES
from .groundedness import GroundednessVerifier
from .harness import EvalHarness, EvalReport
from .metrics.citation_coverage import CitationCoverage
from .metrics.groundedness_metric import GroundednessMetric
from .metrics.injection_resistance import InjectionResistance
from .metrics.latency import Latency
from .metrics.privacy_leak import PrivacyLeak
from .metrics.provider_parity import ProviderParity
from .metrics.recall_at_k import RecallAtK
from .metrics.refusal_correctness import RefusalCorrectness


def default_metrics():
    """The full metric suite (offline first, then live)."""
    return [
        RecallAtK(),
        CitationCoverage(),
        GroundednessMetric(),
        RefusalCorrectness(),
        PrivacyLeak(),
        InjectionResistance(),
        ProviderParity(),
        Latency(),
    ]


def offline_metrics():
    return [m for m in default_metrics() if not getattr(m, "requires_live_model", False)]


__all__ = [
    "Doc",
    "EvalCase",
    "Metric",
    "MetricResult",
    "GOLDEN_CASES",
    "GroundednessVerifier",
    "EvalHarness",
    "EvalReport",
    "default_metrics",
    "offline_metrics",
]
