"""
BDD acceptance layer (000-docs/009 #20) — binds features/acceptance_invariants.feature
to the real code. Fills the L6/L7 gap the audit flagged (0 .feature files): the
moat invariants are now executable, human-readable acceptance specs, not just
prose. Step glue exercises the actual PolicyEngine + RAGPipeline (with the shared
fakes), so a scenario passes only if the invariant genuinely holds.
"""
import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from test_privacy_gate import (  # reuse the vetted fakes
    SECRET_SENTINEL,
    FakeEmbed,
    FakeLLM,
    FakeRetriever,
    _chunk,
)

from nexus.core.config import Config, NexusMode
from nexus.core.models import QueryRequest
from nexus.core.policy import PolicyEngine
from nexus.core.rag_pipeline import RAGPipeline
from nexus.retrieval.citation_verifier import INSUFFICIENT_EVIDENCE_ANSWER

scenarios("../features/acceptance_invariants.feature")

# A non-local provider — what the policy gate treats as cloud egress.
CLOUD = FakeLLM(is_local=False, label="anthropic")


@pytest.fixture
def ctx():
    return {}


# --- policy-gate scenarios ---
@given(parsers.parse('the policy engine is in "{mode}" mode'))
def _engine(ctx, mode):
    ctx["engine"] = PolicyEngine(mode=mode)


@when("a cloud LLM call is guarded")
def _guard_cloud(ctx):
    ctx["decision"] = ctx["engine"].guard_llm("some prompt", CLOUD)


@when("a payload containing an AWS access key is guarded for a cloud LLM")
def _guard_secret(ctx):
    ctx["decision"] = ctx["engine"].guard_llm(f"context {SECRET_SENTINEL}", CLOUD)


@then("the call is blocked")
def _blocked(ctx):
    assert ctx["decision"].allowed is False


@then(parsers.parse('the "{name}" secret pattern is reported'))
def _secret_reported(ctx, name):
    assert name in ctx["decision"].secret_hits


# --- refusal scenario ---
@given(parsers.parse("a pipeline whose top retrieval score is {score:f}"))
def _pipeline(ctx, score, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "CHROMA_DB_PATH", str(tmp_path / "chroma"))
    monkeypatch.setattr(Config, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(Config, "NEXUS_MODE", NexusMode.LOCAL)
    llm = FakeLLM(is_local=True, label="ollama")
    pipe = RAGPipeline(
        llm_provider=llm,
        embed_provider=FakeEmbed(is_local=True),
        workspace_id="bdd",
        retriever=FakeRetriever([_chunk("weakly related", score=score)], is_local=True),
    )
    pipe.policy = PolicyEngine(mode="local")
    ctx["pipe"] = pipe
    ctx["llm"] = llm


@given(parsers.parse("an evidence floor of {floor:f}"))
def _floor(ctx, floor):
    ctx["pipe"].verifier.min_score = floor


@when("the knowledge base is queried")
def _query(ctx):
    ctx["resp"] = ctx["pipe"].query(QueryRequest(question="q?", workspace_id="bdd"))


@then("the answer is the insufficient-evidence refusal")
def _refused(ctx):
    assert ctx["resp"].answer == INSUFFICIENT_EVIDENCE_ANSWER


@then("no citations are returned")
def _no_citations(ctx):
    assert ctx["resp"].citations == []


@then("the language model is never called")
def _llm_not_called(ctx):
    assert ctx["llm"].calls == 0
