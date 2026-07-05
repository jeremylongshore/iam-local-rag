# Testing-Quality Remediation AAR — Intent NEXUS

**Type:** After-Action / Completion Report (AA-AACR)
**Date:** 2026-07-05
**Author:** Intent Solutions
**Scope:** full remediation of the 26 verified findings from the specialist
testing field audit (`009-TQ-AUDT`), shipped as 4 themed PRs.
**Beads:** audit `local-doi`; remediation epic `local-s9e` (children PR1–PR4, all closed).

---

## 1. What this was

A specialist field team (5 lenses + per-finding adversarial verification, 35
agents) audited the merged NEXUS suite and returned **26 verified findings**
(`009-TQ-AUDT`). The verdict: a disciplined suite whose **gates overstated the
assurance they provided**, with the moat invariants thinly exercised exactly
where a regression would be catastrophic — plus one possible real bug. This AAR
records how all 26 were closed.

## 2. Shipped — 4 PRs, each through the full review loop

Every PR: feature branch → PR → Gemini review → comments addressed → green CI →
squash-merge. **8 Gemini comments across the four PRs, every one addressed.**

| PR | GH | Theme | Findings |
|---|---|---|---|
| **PR1** | #12 | Make the gates real | mutmut mutation gate (advisory, `--use-coverage`); truthful CRAP (radon on PATH + `coverage.json`); coverage ratchet 55→65; **fixed a silently-crashing escape-scan gate** (table-format `TESTING.md` under `set -euo pipefail` aborted the scanner) | #1 #2 #3 #10 #11 #17 #19 |
| **PR2** | #13 | Cover the moat | every secret (8) + PII (4) pattern parametrized (positive + near-miss); provider adapters behaviorally tested (SDK-mocked, in the blocking gate); provider-ABC contract; cite-success test; single-gate AST guard | #4 #5 #7 #8 #12 #23 |
| **PR3** | #14 | CI wiring + API hygiene | lazy `get_ledger()` DI + injectable `RAGPipeline` ledger (killed the import- AND construction-time `./nexus_ledger.db` leak); blocking mocked API tests + shared `conftest.py`; CLI `cmd_ask`/`cmd_audit`; two mis-asserting integration tests fixed | #6 #9 #13 #18 #22 #25 #26 |
| **PR4** | #15 | Score bug + property tests + BDD | **ChromaRetriever out-of-[0,1] score bug fixed** (cosine space + clamp); hypothesis property/fuzz (regexes + hash-chain); exact `token_estimate`; PDF ingestion; seed BDD acceptance layer | #14 #15 #16 #20 #21 #24 |

## 3. The needle-movers

- **Gate integrity.** Three "gates" were lying or missing: CRAP scored every method
  at coverage=0 (no `coverage.json`) and scanned `99-Archive/` legacy — the raw
  "avg 10.38 / max 272" collapsed to **4 real `nexus/` blockers** once coverage
  was fed in. Escape-scan had **never run** on this repo (it aborted parsing a
  table-format floor). A mutation gate now exists. These were the findings that
  most undercut "harness-gated CI."
- **Coverage where it matters.** Provider adapters **20–23% → 58–82%**, server.py
  **60% → 71%**, cli.py **72% → 90%**; total **69% → 80%** (floor 55 → 78). The
  moat invariants (one policy gate, secret-block, cited-or-refuse) are now each
  covered by blocking, mutation-sensitive tests.
- **A real bug, not just a test gap (#14).** `ChromaRetriever` emitted relevance
  scores outside [0,1] (a live `-1.83`) because Chroma defaults to L2 distance;
  the `CitationVerifier` evidence floor assumes [0,1], so the refusal decision was
  silently distortable. Fixed with cosine space + a defensive clamp.
- **Test isolation.** A module-import side effect (and a second at pipeline
  construction) wrote a real `./nexus_ledger.db` during the blocking gate; both
  are gone (verified zero strays), via dependency-injected ledgers.

## 4. Engineering calls worth recording

- **Mutation scope = pure-logic modules only.** Whole-file mutmut on `policy.py`
  (regexes) and `ledger.py` (SQL) is dominated by un-killable string mutants and
  overran a 4-min bound. Their assurance comes from **stronger** targeted tests:
  parametrized positive+near-miss boundary tests for the regexes, and physical
  DB-tampering tests for the hash-chain. Mutation stays on `citation_verifier`.
- **CRAP `99-Archive/` inflation is an upstream harness gap** (no exclude config);
  filed as a follow-on, documented in `ci.yml`. Not shipped code.
- **BDD is a seed, not a box-tick.** Three scenarios bound to real code (policy
  gate, secret-block, refusal); grows toward all 7 invariants.

## 5. Residual / follow-on

- Upstream harness asks: CRAP fail-**closed** when radon is absent (#3); a CRAP
  exclude for archived trees.
- Grow the BDD layer to the remaining invariants (privacy receipt, untrusted-text,
  small-commits) and promote the mutation gate from advisory to a kill-rate floor
  once `citation_verifier` is hardened.
- Provider CRAP hotspots that remain are the low-coverage `evals/metrics/*` — a
  natural next coverage target.

## 6. Outcome

**216 unit tests, ~80% coverage, all four PRs merged.** The suite went from
"disciplined but self-overstating" to gates that measure what they claim, the
moat invariants covered where a regression is catastrophic, and the one real bug
fixed. Grade **B → A−**.

---

*Closes epic `local-s9e`. Method + full finding list: `009-TQ-AUDT`. The audit was
run before touching code; every fix shipped through the non-negotiable review loop.*
