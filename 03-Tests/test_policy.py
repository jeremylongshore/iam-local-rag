"""
Unit tests for the PolicyEngine — the single mode-aware outbound gate.

Covers: PII redaction, secret detection, context preparation, and the mode
matrix (LOCAL blocks all external; HYBRID forces local embeddings + blocks
secrets; CLOUD explicit but still blocks secrets).
"""
import pytest

from nexus.core.models import Citation
from nexus.core.policy import (
    PolicyEngine,
    PolicyViolation,
)
from nexus.core.providers.profiles import ProviderPrivacyProfile


class _FakeProvider:
    """Minimal stand-in exposing only what the gate reads."""

    def __init__(self, label: str, is_local: bool):
        self._label = label
        self._is_local = is_local

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label=self._label,
            is_local=self._is_local,
            sends_data_offhost=not self._is_local,
        )


LOCAL = _FakeProvider("ollama", is_local=True)
CLOUD = _FakeProvider("anthropic", is_local=False)

# A realistic AWS access key sentinel (matches the aws_access_key pattern).
SECRET_SENTINEL = "AKIAIOSFODNN7EXAMPLE"


def _cite(text, source="doc.pdf", page=1, chash="hash123"):
    return Citation(
        source=source, page=page, excerpt=text, relevance_score=0.9, content_hash=chash
    )


class TestRedaction:
    def test_redact_email(self):
        engine = PolicyEngine(mode="hybrid")
        red, redactions = engine.redact_pii("contact me at jane@example.com please")
        assert "jane@example.com" not in red
        assert "[REDACTED:email]" in red
        assert any(r.kind == "email" and r.count == 1 for r in redactions)

    def test_redact_ssn(self):
        engine = PolicyEngine(mode="hybrid")
        red, redactions = engine.redact_pii("SSN 123-45-6789 on file")
        assert "123-45-6789" not in red
        assert any(r.kind == "ssn" for r in redactions)

    def test_clean_text_untouched(self):
        engine = PolicyEngine(mode="hybrid")
        red, redactions = engine.redact_pii("the quick brown fox")
        assert red == "the quick brown fox"
        assert redactions == []


class TestSecretScan:
    def test_detects_aws_key(self):
        engine = PolicyEngine(mode="hybrid")
        hits = engine.scan_secrets(f"here is a key {SECRET_SENTINEL} oops")
        assert "aws_access_key" in hits

    def test_detects_openai_key(self):
        engine = PolicyEngine(mode="hybrid")
        hits = engine.scan_secrets("token sk-" + "a" * 40)
        assert "openai_key" in hits

    def test_scan_returns_names_not_values(self):
        engine = PolicyEngine(mode="hybrid")
        hits = engine.scan_secrets(SECRET_SENTINEL)
        # Never leak the secret value itself in the finding.
        assert SECRET_SENTINEL not in hits


class TestPrepareContext:
    def test_source_attribution_and_hash(self):
        engine = PolicyEngine(mode="hybrid", hybrid_safe_mode=True, max_snippet_length=1000)
        bundle = engine.prepare_context([_cite("This is some content", source="document.pdf", page=5)])
        assert "[Source: document.pdf, Page 5]" in bundle.safe_context
        assert "This is some content" in bundle.safe_context
        assert len(bundle.excerpt_hashes) == 1

    def test_capping_in_safe_mode(self):
        engine = PolicyEngine(mode="hybrid", hybrid_safe_mode=True, max_snippet_length=100)
        bundle = engine.prepare_context([_cite("A" * 500)])
        assert "..." in bundle.safe_context
        assert "A" * 500 not in bundle.safe_context

    def test_pii_redacted_in_context(self):
        engine = PolicyEngine(mode="hybrid", max_snippet_length=1000)
        bundle = engine.prepare_context([_cite("email jane@example.com here")])
        assert "jane@example.com" not in bundle.safe_context
        assert any(r.kind == "email" for r in bundle.redactions)

    def test_hash_is_of_full_pre_redaction_text(self):
        engine = PolicyEngine(mode="hybrid", max_snippet_length=50)
        full = "A" * 200
        bundle = engine.prepare_context([_cite(full)])
        assert bundle.excerpt_hashes[0] == engine._hash(full)


class TestModeGate:
    # --- LOCAL: zero external calls, fail-closed ---
    def test_local_blocks_cloud_llm(self):
        engine = PolicyEngine(mode="local")
        decision = engine.guard_llm("anything", CLOUD)
        assert decision.allowed is False
        assert "LOCAL mode" in decision.reason

    def test_local_blocks_cloud_embedding(self):
        engine = PolicyEngine(mode="local")
        decision = engine.guard_embedding(["chunk a", "chunk b"], CLOUD)
        assert decision.allowed is False

    def test_local_allows_local_llm(self):
        engine = PolicyEngine(mode="local")
        decision = engine.guard_llm("anything", LOCAL)
        assert decision.allowed is True
        assert decision.is_local is True

    # --- HYBRID: local embeddings forced, secrets blocked ---
    def test_hybrid_blocks_cloud_embedding(self):
        engine = PolicyEngine(mode="hybrid")
        decision = engine.guard_embedding(["corpus chunk"], CLOUD)
        assert decision.allowed is False
        assert "local embeddings" in decision.reason

    def test_hybrid_allows_local_embedding(self):
        engine = PolicyEngine(mode="hybrid")
        decision = engine.guard_embedding(["corpus chunk"], LOCAL)
        assert decision.allowed is True

    def test_hybrid_allows_clean_cloud_llm(self):
        engine = PolicyEngine(mode="hybrid")
        decision = engine.guard_llm("a perfectly normal question and context", CLOUD)
        assert decision.allowed is True

    def test_hybrid_blocks_secret_in_cloud_llm(self):
        engine = PolicyEngine(mode="hybrid")
        decision = engine.guard_llm(f"context contains {SECRET_SENTINEL}", CLOUD)
        assert decision.allowed is False
        assert "aws_access_key" in decision.secret_hits

    # --- CLOUD: explicit egress, but never secrets ---
    def test_cloud_allows_clean_payload(self):
        engine = PolicyEngine(mode="cloud")
        decision = engine.guard_llm("normal text", CLOUD)
        assert decision.allowed is True

    def test_cloud_blocks_secret(self):
        engine = PolicyEngine(mode="cloud")
        decision = engine.guard_llm(f"leak {SECRET_SENTINEL}", CLOUD)
        assert decision.allowed is False


class TestEnforceAndReceipt:
    def test_enforce_raises_on_block(self):
        engine = PolicyEngine(mode="local")
        decision = engine.guard_llm("x", CLOUD)
        with pytest.raises(PolicyViolation):
            engine.enforce(decision)

    def test_enforce_passes_on_allow(self):
        engine = PolicyEngine(mode="local")
        decision = engine.guard_llm("x", LOCAL)
        assert engine.enforce(decision) is decision

    def test_receipt_shape(self):
        engine = PolicyEngine(mode="hybrid")
        decision = engine.guard_llm("hello world", CLOUD, model="claude-x")
        receipt = decision.as_receipt()
        assert receipt["policy_pass"] is True
        assert receipt["destination"] == "cloud"
        assert receipt["provider"] == "anthropic"
        assert receipt["chars_out"] == len("hello world")
        assert receipt["tokens_out_estimate"] >= 1

    def test_get_policy_summary(self):
        engine = PolicyEngine(mode="hybrid", hybrid_safe_mode=True, max_snippet_length=2000)
        summary = engine.get_policy_summary()
        assert summary["mode"] == "hybrid"
        assert summary["hybrid_safe_mode"] is True
        assert summary["max_snippet_length"] == 2000
        assert summary["policy_enforced"] is True
