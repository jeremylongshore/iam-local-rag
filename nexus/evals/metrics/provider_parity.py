"""
ProviderParity metric (LIVE — requires a real Ollama model).

For every factual case that declares `must_contain` expectations, run the real
RAGPipeline twice against a live OllamaLLMProvider (two independent runs, each on
a freshly built pipeline). A run "passes" when its answer contains every
must_contain token (case-insensitive). The score is the fraction of runs that
pass across all applicable cases (2 runs per case). Two independent passes over a
local model surface non-determinism / model drift: a well-grounded factual answer
should reproduce the expected tokens on both runs.
"""
from __future__ import annotations

from typing import List, Tuple

from ..base import EvalCase, MetricResult
from ..fakes import build_eval_pipeline

_RUNS = 2


class ProviderParity:
    name = "provider-parity"
    # Informational: parity measures MODEL determinism (drift), which NEXUS does
    # not control, so it reports a score but never fails the suite. Small models
    # score lower; use it to compare providers, not to gate NEXUS correctness.
    threshold = 0.8
    requires_live_model = True
    informational = True

    def _applicable(self, case: EvalCase) -> bool:
        if case.should_refuse or case.secret_sentinel:
            return False
        return bool(case.must_contain)

    def _run_once(self, case: EvalCase, tokens: List[str]) -> Tuple[bool, dict]:
        from ...core.models import QueryRequest
        from ...core.providers.ollama_provider import OllamaLLMProvider

        try:
            pipe = build_eval_pipeline(case, mode="local")
            pipe.llm_provider = OllamaLLMProvider()
            resp = pipe.query(
                QueryRequest(question=case.question, workspace_id="eval", max_results=3)
            )
        except Exception as exc:  # noqa: BLE001 - a failed run contains no tokens
            return False, {"ok": False, "error": str(exc)}

        answer = resp.answer.lower()
        ok = all(tok in answer for tok in tokens)
        return ok, {"ok": ok}

    def evaluate(self, cases: List[EvalCase]) -> MetricResult:
        applicable = [c for c in cases if self._applicable(c)]
        if not applicable:
            return MetricResult(
                name=self.name,
                score=1.0,
                passed=True,
                detail="no factual must_contain cases",
                n=0,
            )

        per_case: List[dict] = []
        total_runs = 0
        passed_runs = 0
        answerable_cases = 0  # >=1 of the runs produced a correct answer
        for case in applicable:
            tokens = [t.lower() for t in case.must_contain]
            runs: List[dict] = []
            case_ok = 0
            for _ in range(_RUNS):
                total_runs += 1
                ok, note = self._run_once(case, tokens)
                if ok:
                    passed_runs += 1
                    case_ok += 1
                runs.append(note)
            if case_ok >= 1:
                answerable_cases += 1
            per_case.append(
                {"id": case.id, "must_contain": case.must_contain, "answerable": case_ok >= 1, "runs": runs}
            )

        # Drift score is informational; the GATE is the "answerable" floor: every
        # factual case must produce a correct grounded answer on at least one run,
        # so a pipeline that can never answer correctly still fails.
        score = passed_runs / total_runs if total_runs else 1.0
        answerable = answerable_cases == len(applicable)
        return MetricResult(
            name=self.name,
            score=score,
            passed=answerable,
            detail=f"answerable={answerable_cases}/{len(applicable)} cases; drift-score "
            f"[informational] {passed_runs}/{total_runs} runs matched, {_RUNS} runs each",
            n=len(applicable),
            per_case=per_case,
        )
