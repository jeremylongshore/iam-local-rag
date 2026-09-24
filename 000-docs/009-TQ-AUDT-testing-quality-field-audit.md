# Testing-Quality Field Audit — Intent NEXUS

**Type:** Testing & Quality / Audit Report (TQ-AUDT)
**Date:** 2026-07-05
**Author:** Intent Solutions
**Scope:** the merged NEXUS product on `master` (post P0–P7, ~150 tests), audited
against the 7-layer testing taxonomy — unit, acceptance, regression, CRAP,
Gherkin/BDD, coverage, mutation, hygiene.
**Baseline:** `007-AA-AUDR-architecture-audit.md` · **AAR:** `008-AA-AACR-implementation-aar.md`
**Beads:** audit `local-doi`; remediation epic `local-s9e` (children PR1–PR4).

---

## 1. Method — a specialist field team, adversarially verified

Five specialist agents audited the *merged* product in parallel, each owning a
dimension, then **every finding was independently adversarially verified** (a
separate agent tried to refute it against the real repo) before it counted:

| Dimension | Specialist lens |
|---|---|
| Deterministic gates | quality-gate-runner (ran coverage, radon CRAP, bias, gherkin-lint) |
| Unit discipline | kent-beck-reviewer (tautology / mock-the-SUT / assertion strength) |
| Acceptance & traceability | test-automator (the 7 invariants → executable tests) |
| Regression & integration | test-automator (untested modules, CI wiring, missing layers) |
| Test hygiene | code-reviewer (isolation, flakiness, brittleness, side effects) |

**35 agents, 0 errors. 30 raw findings → 26 confirmed** (4 refuted by the verify
pass). The suite is genuinely disciplined where it counts — the privacy tests
assert `provider.calls == 0` (proving the block happens *before* egress), the
ledger tests physically corrupt the DB and assert tamper detection, and recall@k
places the relevant doc *last* to be anti-tautological. The findings below are
what a trust product still can't afford to leave unmeasured.

## 2. Measurements (deterministic gates)

- **Unit coverage:** 69% total (CI floor only 55% → no ratchet protection).
  Worst modules: `vertex_provider` 20%, `openai_provider` 21%, `anthropic_provider`
  23%, `injection_resistance` metric 26% — i.e. the outbound path the policy gate
  guards is the *least* covered.
- **CRAP:** the gate **FAILS** on real radon — production avg 10.38 > 10.0, **max
  272**, 28 methods over threshold, concentrated in the provider
  `generate_with_messages` methods. `audit-harness crap` **silently returns
  `pass:true` when radon is not on PATH** (a false green).
- **Mutation testing:** ABSENT — no mutmut/cosmic-ray installed or configured.
- **Test bias:** 14 smoke-only `is not None` assertions ≈ 9.4 / 100 tests (over the
  5/100 P1 line).
- **Gherkin/BDD:** 0 `.feature` files (documented waiver in `tests/TESTING.md`).

## 3. Confirmed findings (26), ranked

### HIGH (9)

1. **No mutation gate** — assertion strength is entirely unmeasured; coverage is
   the only signal and coverage can't distinguish a real assertion from `is not None`.
2. **CRAP gate FAILS on real radon** (avg 10.38, max 272, 28 blockers) — provider
   call paths carry acceptance invariant #1 yet are the highest-complexity,
   lowest-coverage code.
3. **`audit-harness crap` false-green** — prints "radon not installed" to stderr
   yet returns `pass:true` / exit 0. Fail-open gate. *(Upstream harness bug —
   filed as a follow-on; in-repo we make CI run it against the venv radon.)*
4. **6 of 8 secret-egress regexes have zero test coverage** — invariant #6 (never
   ship a credential) is 25% exercised; only `aws_access_key` + `openai_key` are hit.
5. **Only the *refuse* half of cited-or-refuse is enforced at merge time** — the
   cite-success assertion lives in an integration-marked (non-blocking) test.
6. **The only full end-to-end integration suite is `continue-on-error: true`** —
   policy-gate + ledger + retrieval wiring regressions cannot fail CI.
7. **Cloud provider adapters get zero execution in any CI job** (20–23% coverage) —
   `test_router.py` only asserts `isinstance` + constructor fields.
8. **No contract test across the provider ABC** that `PolicyEngine` trusts for the
   local/cloud (`is_local`) classification.
9. **Import-time filesystem side effect** — `nexus/api/server.py` builds
   `_ledger = RunLedger()` at module import, writing a real `./nexus_ledger.db` in
   the cwd; `test_api_auth.py` (blocking gate) then reads/writes the real ledger.

### MEDIUM (10)

10. Coverage floor 55% vs actual 69% — no ratchet; masks collapse in provider code.
11. 14 smoke-only `is not None` assertions (~9.4/100, over the P1 line).
12. 2 of 4 PII patterns (`phone`, `credit_card`) never exercised with a match.
13. Two integration tests named for redaction/truncation assert neither
    (mutation-insensitive — the redaction path could be deleted and they'd pass).
14. **`ChromaRetriever` emits relevance scores outside [0,1]** (a live `-1.83`);
    the `CitationVerifier` evidence floor depends on those scores and the test
    hides it by asserting only ordering. **Possible real normalization bug.**
15. Invariant 5 (untrusted retrieved text) — the end-to-end "LLM won't obey
    injection" guarantee is `requires_live_model` and unreachable from CI.
16. Zero property/fuzz testing of the policy regexes or the ledger hash-chain.
17. No mutation testing; the CRAP gate that references it is silently broken (dup lens of #1/#3).
18. CLI `cmd_ask` / `cmd_audit` (the primary user-facing commands) functionally untested.
19. Coverage floor masks collapse in policy-adjacent eval metrics (dup lens of #10).

### LOW (7)

20. No `.feature` files — no executable BDD tying the 7 invariants to scenarios (waiver).
21. `token_estimate` asserted only `>= 1` where the exact value is computable.
22. Refusal-path privacy-receipt emission is never asserted; field is typed Optional.
23. Invariant 1 (single gate) has no static/AST regression-guard against a future 2nd path.
24. PDF ingestion branch (`PyPDFLoader`) untested (only `.txt`/`.md` exercised).
25. `test_api.py` leaks temp dirs via `tempfile.mkdtemp()` with no cleanup.
26. Inconsistent temp-resource pattern (tempfile module vs. `tmp_path` fixture).

## 4. Remediation plan — 4 themed PRs (epic `local-s9e`)

Each PR ships through the non-negotiable loop: feature branch → PR → bot review →
comments addressed → green CI → squash-merge.

- **PR1 — Make the gates real** (`local-ymq`): mutmut mutation gate (advisory
  baseline) on policy/ledger/citation_verifier; CI runs `audit-harness crap`
  against the venv radon (truthful); coverage floor ratchet 55→65; TESTING.md gate
  table; this audit doc. *(#1 #2 #3 #10 #11 #17 #19)*
- **PR2 — Cover the moat** (`local-63g`): parametrized all-8-secret + 4-PII tests;
  provider-adapter tests (mock SDKs) — which also crush the CRAP hotspots via
  coverage; provider-ABC contract test; cite-success unit test; single-gate AST
  guard. *(#4 #5 #7 #8 #12 #23)*
- **PR3 — CI wiring + API hygiene** (`local-b7u`): lazy/DI ledger (kill the
  import-time side effect); mocked-provider API tests in the blocking gate;
  refusal-path receipt assertion; fix the two mis-asserting tests; `tmp_path`
  hygiene; CLI `cmd_ask`/`cmd_audit` tests. *(#6 #9 #13 #18 #22 #25 #26)*
- **PR4 — Score bug + property tests + BDD** (`local-wnk`): investigate + fix the
  out-of-[0,1] relevance scores (code, not just the test); hypothesis property/fuzz
  for the regexes + hash-chain; exact `token_estimate` assertion; PDF ingestion
  test; optional `features/` BDD layer for the 7 invariants; final ratchet + AAR.
  *(#14 #15 #16 #20 #21 #24)*

## 5. What the audit did NOT find

No fabricated tests, no disabled/skipped assertions hiding failures, no coverage
gaming, no secret in the test corpus, no tautological metric surviving (the P5
adversarial review had already caught those). The gaps are honest under-coverage
and gate-integrity issues — not deception.

---

*Recorded from the specialist field-team audit run (`wf_dfbfb133-e8a`). The suite
was strong enough that the findings are about raising an already-disciplined bar,
not rescuing a broken one.*
