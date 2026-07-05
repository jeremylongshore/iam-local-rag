# Implementation AAR — Intent NEXUS local-first BYOK refactor (P0–P6)

**Type:** After-Action / Completion Report (AA-AACR)
**Date:** 2026-07-04
**Author:** Intent Solutions
**Scope:** the refactor from a naive local-RAG app into a local-first / hybrid /
cloud-BYOK document-intelligence platform. Baseline: `007-AA-AUDR-architecture-audit.md`.
Beads epic: `local-6p0`.

---

## 1. What NEXUS is now

A **usable, trustworthy local-first BYOK document-intelligence agent.** You point
it at your documents and query them from a CLI; it runs fully local by default,
lets you bring your own cloud model when you choose, and **enforces + measures** a
trust layer on every call: verifiable citations, code-enforced refusal, a
mode-aware policy gate, a per-query privacy receipt, a tamper-evident audit ledger,
injection defense, and a built-in eval harness.

Verified end-to-end on small local models (`qwen2.5:0.5b` + `nomic-embed-text`):
grounded, cited answers with zero cloud egress in LOCAL mode, secrets blocked
before any cloud call, and an intact audit chain.

## 2. What shipped, by phase (all merged to `master`)

| Phase | PR | Delivered |
|---|---|---|
| **P0** — audit + hygiene | #6 | Architecture audit; git reconcile; `pyproject.toml` + CI repair; **overclaim/fabrication scrub** (deleted a fabricated HIPAA-healthcare-client line + HIPAA/GDPR/SOC 2 claims); legacy quarantine; in-repo audit harness. |
| **P1–2** — dangerous bugs | #6 | Embedding-crash fix (adapter over the provider ABC); **ungated corpus→cloud leak closed**; the length-truncator replaced by a mode-aware **PolicyEngine**; provider capability/cost/privacy profiles + fallback; privacy receipts. |
| **P3** — retrieval | #7 | Modular `Retriever` (Chroma real relevance scores + the homegrown **qmd** hybrid backend), `CitationVerifier` (code-enforced refusal), dedicated embed model, `langchain-ollama`/`langchain-chroma` migration, small-model defaults. |
| **P4a** — trust integrity + API | #8 | **Tamper-evident hash-chained ledger** (ICO pattern) + `verify_chain` + gated DELETE; **API-key auth** (constant-time) + **CORS allowlist** + `/audit/verify`. |
| **P4b + P5** — injection + evals | #9 | **`nexus/evals` harness** (recall@k, citation coverage, groundedness, refusal, privacy-leak, injection, provider parity, latency); **prompt-injection scrubber**. |
| **P6 (part 1)** — CLI | #10 | The **`nexus` CLI** (index/ask/policy/providers/config/eval/audit), agent-safe (path confinement, no shell, policy-gated). |

## 3. How it was built — the review discipline (load-bearing)

Every PR ran the same non-negotiable loop: **ultracode adversarial review → PR →
GitHub bot review (Gemini) → comments addressed → green CI → squash-merge.**

The adversarial review was not ceremony — it caught real, high-severity defects
that would otherwise have shipped as false confidence:

- **P3:** the qmd backend silently mapped failures to false "insufficient evidence"
  refusals; CLI argument-injection via a dash-prefixed query; incomplete workspace
  isolation. (8 findings.)
- **P4:** a non-injective hash-chain canonical serialization (re-attribution
  attack); non-constant-time key comparison; `verify_chain` overclaim. (6 findings.)
- **P5 (most valuable):** the parallel-agent-built metrics were **tautological**
  (`k ≥ corpus` → always 1.0), groundedness turned a *broken* pipeline into a PASS,
  and the injection scrubber was **corrupting legitimate document prose**. (8 findings.)
- **P6:** the path-confinement threat model (its own root is agent-controllable via
  `--allow-root`/env — an operator, not an agent-trusted, control). (6 findings.)

Gemini independently added correctness/security findings on each PR (path traversal,
CORS wildcard detection, injection bypasses, refusal groundedness, …), all addressed.

**Ultracode was also used to build:** the 8 eval-metric modules (P5) were authored
by 8 parallel agents against a hand-authored foundation, then hardened by the
adversarial review above.

## 4. Implemented vs. deferred

**Implemented + tested + merged:** everything in §2. ~150 unit tests + a live
integration suite, ruff-clean, harness-gated CI, 5 auto-released versions.

**Deferred (tracked as beads / roadmap):**
- **P6 remainder** (`local-6p0.12`): round out API endpoints (`/providers`,
  `/policy/preview`, `/config/summary`, `/evals/run`), a Streamlit **privacy meter**,
  and an **optional MCP layer** (disabled-by-default, allowlist, exposing only safe
  params — never `--allow-root`/shell).
- **Groundedness as an inline pipeline gate** (the verifier exists + is eval'd +
  refusal-safe; wiring it before the final answer is a small follow-on).
- **Stronger trust primitives:** an HMAC/external-anchor chain head to catch
  coordinated tail-truncation; a learned/NLI groundedness scorer; a richer
  injection corpus; per-tenant workspace ACLs.

## 5. Residual risks (honest)

- **Injection defense is best-effort.** The scrubber is pattern-based (bypassable);
  the primary control is the untrusted-context prompt boundary. Small models remain
  the weakest link — the eval harness exists precisely to track this.
- **PII/secret regexes are heuristic v1** — high-confidence secrets, best-effort PII.
- **API is single-tenant.** Auth gates access; there is no per-key workspace ACL yet.
- **qmd backend is heavyweight** (compiles a native runtime, runs LLM query
  expansion) and opt-in; Chroma is the zero-dependency default.
- **The `nexus index` guardrail assumes a trusted operator channel** for
  `--allow-root`/env — an MCP wrapper must expose only `paths`.

## 6. Short competitive review

Versus an ordinary local-RAG app (LangChain + Chroma + a Streamlit box):

| Dimension | Ordinary local-RAG | Intent NEXUS |
|---|---|---|
| Egress control | ad-hoc / none | one policy gate, LOCAL zero-egress enforced fail-closed |
| Secrets to cloud | uncontrolled | blocked before any external call |
| Citations | often positional/fake scores | real relevance scores + code-enforced refusal |
| Provenance | none | per-query privacy receipt + tamper-evident hash-chained ledger |
| Injection | prompt-only, untested | scrubber + boundary + a scored eval metric |
| Quality | vibes | a self-run eval harness (recall/citation/groundedness/leak/injection) |
| Portability | provider-coupled | thin BYOK adapters, no agent-SDK lock-in, qmd/Chroma pluggable |
| Interface | a UI script | an agent-safe `nexus` CLI + authed API + UI |

The moat is the trust layer, not the chatbot.

## 7. Next 5 tasks

1. Round out the API endpoints (`local-6p0.12`) — reviewed PR.
2. Streamlit **privacy meter** (visualize the receipt: "0 chars to cloud" / "blocked: secret").
3. Optional **MCP layer** — disabled-by-default, allowlist, safe-params-only.
4. Wire the **groundedness verifier as an inline pipeline gate** (refuse ungrounded answers).
5. Harden the trust primitives — HMAC chain anchor + a learned groundedness scorer.

---

*Recorded at the completion of the core-moat build (P0–P6). Beads epic `local-6p0`;
running narrative in the git history + the CROSS-SESSION-LOG.*
