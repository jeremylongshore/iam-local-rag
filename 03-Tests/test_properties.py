"""
Property-based / fuzz tests (000-docs/009 #16). Before this, the policy regexes
and the ledger hash-chain were each exercised with one hand-picked example.
Hypothesis drives thousands of inputs to prove the invariants that actually
matter: the scrub/redact/scan functions never crash and never let a matched
secret survive, and the audit hash is deterministic + injective on field
boundaries (the re-attribution attack the JSON serialization is designed to stop).
"""
from hypothesis import assume, given
from hypothesis import strategies as st

from nexus.core.ledger import RunLedger
from nexus.core.policy import PolicyEngine

_ENGINE = PolicyEngine(mode="hybrid")

AWS_SENTINEL = "AKIAIOSFODNN7EXAMPLE"  # matches \bAKIA[0-9A-Z]{16}\b


# --------------------------------------------------------------------------- #
# PolicyEngine — total functions, no crashes, no secret survives a match.
# --------------------------------------------------------------------------- #
@given(st.text())
def test_scrub_injection_is_total(text):
    out, n = _ENGINE.scrub_injection(text)
    assert isinstance(out, str)
    assert n >= 0


@given(st.text())
def test_redact_pii_is_total(text):
    out, reds = _ENGINE.redact_pii(text)
    assert isinstance(out, str)
    assert all(r.count >= 1 for r in reds)


@given(st.text())
def test_scan_secrets_returns_only_known_names(text):
    hits = _ENGINE.scan_secrets(text)
    assert all(name in PolicyEngine._SECRET_PATTERNS for name in hits)


@given(prefix=st.text(), suffix=st.text())
def test_aws_sentinel_detected_under_any_surrounding_text(prefix, suffix):
    # Space-delimited so the \b boundaries always hold; the sentinel must be
    # detected no matter what noise surrounds it.
    payload = f"{prefix} {AWS_SENTINEL} {suffix}"
    assert "aws_access_key" in _ENGINE.scan_secrets(payload)


@given(st.text())
def test_injected_email_never_survives_redaction(text):
    payload = f"{text} someone@example.com end"
    out, reds = _ENGINE.redact_pii(payload)
    assert "someone@example.com" not in out
    assert any(r.kind == "email" for r in reds)


# --------------------------------------------------------------------------- #
# Ledger hash-chain — deterministic, prev-sensitive, boundary-injective.
# --------------------------------------------------------------------------- #
_FIELD = st.text(max_size=64)


@given(_FIELD, _FIELD, _FIELD, _FIELD, _FIELD, _FIELD)
def test_row_hash_is_deterministic(ts, op, rid, ws, ph, prev):
    a = RunLedger._compute_row_hash(ts, op, rid, ws, ph, prev)
    b = RunLedger._compute_row_hash(ts, op, rid, ws, ph, prev)
    assert a == b
    assert len(a) == 64  # sha256 hex


@given(_FIELD, _FIELD, _FIELD, _FIELD, _FIELD, _FIELD, _FIELD)
def test_row_hash_depends_on_prev(ts, op, rid, ws, ph, prev1, prev2):
    assume(prev1 != prev2)
    assert RunLedger._compute_row_hash(ts, op, rid, ws, ph, prev1) != (
        RunLedger._compute_row_hash(ts, op, rid, ws, ph, prev2)
    )


@given(st.text(min_size=1, max_size=32), st.text(min_size=1, max_size=32), st.text(min_size=1, max_size=32))
def test_row_hash_no_field_boundary_forgery(a, b, c):
    # (run_id=a, workspace_id="b::c") and (run_id="a::b", workspace_id=c) are
    # DIFFERENT audit facts; a naive "join with a delimiter" scheme would collide
    # them. The injective JSON serialization must keep the hashes distinct.
    h1 = RunLedger._compute_row_hash("t", "op", a, f"{b}::{c}", "ph", "prev")
    h2 = RunLedger._compute_row_hash("t", "op", f"{a}::{b}", c, "ph", "prev")
    assert h1 != h2
