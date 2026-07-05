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


def test_groundedness_verifier_detects_hallucination():
    v = GroundednessVerifier(threshold=0.6)
    context = ["The Eiffel Tower is in Paris, France, and is 330 metres tall."]
    grounded = "The Eiffel Tower is in Paris and is 330 metres tall."
    hallucinated = "The Statue of Liberty stands in Tokyo Japan and weighs nine thousand tons."
    assert v.score(grounded, context) >= 0.6
    assert v.score(hallucinated, context) < 0.6  # unsupported claims score low


def test_recall_is_earned_not_tautological():
    from nexus.evals.base import Doc, EvalCase
    from nexus.evals.metrics.recall_at_k import RecallAtK

    # Relevant doc is LAST among 6 (position > k); only a working keyword ranker
    # surfaces it into the top-3, so a passing score proves ranking is exercised.
    case = EvalCase(
        id="zebra",
        question="tell me about zebra black and white stripes",
        docs=[
            Doc("a.txt", "Clouds are white and float in the sky."),
            Doc("b.txt", "Cars have four wheels and an engine."),
            Doc("c.txt", "Soup is served hot in a bowl."),
            Doc("d.txt", "Rocks are hard and heavy."),
            Doc("e.txt", "Rain makes the ground wet."),
            Doc("z.txt", "A zebra has black and white stripes.", is_relevant=True),
        ],
    )
    r = RecallAtK().evaluate([case])
    assert r.score == 1.0  # earned: the ranker found the relevant doc despite it being last
