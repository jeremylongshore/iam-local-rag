"""
Unit tests for the nexus.evals harness (offline metrics only — no Ollama).
"""
from nexus.evals import (
    GOLDEN_CASES,
    EvalHarness,
    GroundednessVerifier,
    default_metrics,
    offline_metrics,
)
from nexus.evals.base import MetricResult
from nexus.evals.metrics.privacy_leak import PrivacyLeak
from nexus.evals.metrics.recall_at_k import RecallAtK


def test_offline_suite_runs_and_passes():
    report = EvalHarness(GOLDEN_CASES).run(offline_metrics(), include_live=False)
    assert report.results
    assert all(isinstance(r, MetricResult) for r in report.results)
    assert report.passed, "\n" + report.render()


def test_privacy_leak_always_blocks_secret():
    r = PrivacyLeak().evaluate(GOLDEN_CASES)
    assert r.passed and r.score == 1.0  # planted secret blocked before any cloud call


def test_recall_at_k_finds_relevant_docs():
    r = RecallAtK().evaluate(GOLDEN_CASES)
    assert r.score >= 0.8


def test_harness_skips_live_metrics_by_default():
    report = EvalHarness(GOLDEN_CASES).run(default_metrics(), include_live=False)
    names = {r.name for r in report.results}
    assert "recall_at_k" in names
    assert "injection-resistance" not in names  # live-only, skipped offline


def test_groundedness_verifier():
    v = GroundednessVerifier(threshold=0.5)
    assert v.score("Paris France tower", ["The Eiffel Tower is in Paris, France."]) > 0.5
    assert v.score("", ["anything"]) == 1.0  # empty/refusal answer is trivially grounded
    assert v.is_grounded("Paris city", ["Paris is a city in France"])
