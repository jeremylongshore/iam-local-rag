# Architecture Audit — Intent NEXUS (local-rag-agent / iam-local-rag)

**Type:** After-Action / Audit-Review (AA-AUDR)
**Date:** 2026-07-04
**Author:** Intent Solutions
**Status:** Baseline audit for the local-first BYOK refactor (beads epic `local-6p0`)
**Scope of this doc:** ground-truth findings + the gap→phase map that drives the refactor. This is the "start here" truth for anyone (Ope's agent, Jeremy's, a contributor) picking up NEXUS.

---

## 0) Canonical identity (state once, drift never again)

One product, three names — do not invent a fourth:

| Layer | Value |
|---|---|
| **Product name** | **Intent NEXUS** (product "NEXUS" under the Intent Solutions house brand) |
| **Local directory** | `~/000-projects/local-rag-agent` |
| **GitHub remote** | `jeremylongshore/iam-local-rag` |

The README install/clone URL used the wrong slug `nexus-rag` (which is not a real repo) in **9 places** across `README.md`, `.github/workflows/ci.yml`, and `000-docs/003-DR-REFF-readme.md`. Canonical is `iam-local-rag`. There is **no `install.sh` at repo root** (only `05-Scripts/install.sh`), so the one-line-installer promise is doubly broken — the quickstart should use `git clone https://github.com/jeremylongshore/iam-local-rag.git`.

**Positioning (the target):** *Local-first BYOK document intelligence with verifiable citations, privacy receipts, provider portability, and policy-bounded cloud acceleration.* Not "the shiniest chatbot" — the moat is the trust layer.

---

## 1) What is good (reuse, do not rebuild)

| Asset | Where | Why it is worth keeping |
|---|---|---|
| Clean provider ABCs | `nexus/core/providers/base.py` | `LLMProvider` / `EmbeddingProvider` abstract base classes with the right method surface (`embed_documents`/`embed_query`, `generate`/`generate_with_messages`, `is_available`). |
| **Lazy cloud-SDK isolation** | `providers/{anthropic,openai,vertex}_provider.py` | Each cloud SDK is imported *inside* `_get_client()`, so `import nexus` pulls **no** cloud SDK. Verified: importing core is clean. Keep this discipline. |
| 4 real LLM providers with retry | `providers/*.py` | Ollama, Anthropic, OpenAI, Vertex all implement generate + exponential-backoff retry on 429/5xx. Real, not stubbed. |
| Real BYOK secret handling | `config.py`, `.env` gitignored | Keys are env-only, no hardcoded secrets, `.env` in `.gitignore`. |
| Working SQLite audit ledger | `nexus/core/ledger.py` | Records index + query runs per workspace with excerpt hashes. (Not yet tamper-evident — see §2 / P4.) |
| Authoritative doc set | `000-docs/` | Already v4.2-filed (`NNN-CC-ABCD`). This is the canonical docs home; `01-Docs/` is stale (see §3). |

---

## 2) What is broken or dangerous (fixed THIS pass — Phase 1-2)

Each finding is grounded to a file:line verified 2026-07-04.

### 2.1 OpenAI / Vertex embeddings crash today  — **crash**
`rag_pipeline.py:79` and `:139` call `self.embed_provider._get_embeddings()` — a **private, Ollama-only** method. Only `OllamaEmbeddingProvider` defines `_get_embeddings()` (it returns a LangChain `OllamaEmbeddings` object for Chroma). `OpenAIEmbeddingProvider` and `VertexEmbeddingProvider` do **not** have it. Result: `NEXUS_EMBED_PROVIDER=openai` (or `vertex`) → `AttributeError` on both index and query.
**Fix:** a small LangChain `Embeddings` adapter over the ABC (`embed_documents`/`embed_query`), passed to Chroma, so all providers work uniformly. Stop calling the private method.

### 2.2 Ungated embeddings-to-cloud leak  — **the real privacy hole**
`index_documents` (`rag_pipeline.py:86-161`) embeds **every chunk of the entire corpus** with **no policy check**. And `router.py:102-109` only forces local (Ollama) embeddings in **LOCAL** mode — **HYBRID does not force local embeddings**. So in the default `NEXUS_MODE=hybrid`, if `NEXUS_EMBED_PROVIDER` is a cloud provider, the whole document corpus ships to a cloud embedding API — the exact thing "docs stay local" promises never happens.
**Fix:** one mode-aware policy gate on *all* outbound calls (LLM **and** embeddings); HYBRID/LOCAL force local embeddings (fail-closed); the embed step in `index_documents` routes through the gate.

### 2.3 "PolicyRedactor" is a truncator + hasher, not a redactor  — **privacy theater**
`policy.py` `PolicyRedactor`:
- No PII/secret redaction at all — it only truncates to `MAX_SNIPPET_LENGTH` and SHA-256-hashes.
- Default `MAX_SNIPPET_LENGTH=4000` (`config.py:88`) > `CHUNK_SIZE=1000` (`config.py:66`), so it **truncates nothing** by default.
- Bypassable: gated on `HYBRID_SAFE_MODE`, which is `false`-able via env (`config.py:87`).
- `validate_outbound_payload` only length-checks + optional test sentinel; it does not scan for secrets.
**Fix:** replace with a `PolicyEngine` that is `NexusMode`-driven, redacts real PII/secret patterns, caps snippets, and runs a payload inspector that **blocks on violation** (see §4 invariants 1, 2, 6).

### 2.4 No prompt-injection defense  — **untrusted-data-as-instructions**
Retrieved document text is interpolated raw into the prompt template (`rag_pipeline.py:201-215`, `Context: {context}`). A malicious document can carry instructions the model will follow.
**Fix (this pass = boundary; full hardening = P4):** wrap retrieved context in an explicit untrusted-data boundary and instruct the model to treat it as data, never instructions. Injection corpus + eval = P4/P5.

### 2.5 Ledger is not tamper-evident  — **audit integrity**
`ledger.py` uses plain `INSERT`s and exposes a `DELETE` path (`cleanup_old_runs`, `ledger.py:352-362`). No hash chain → an audit row can be altered/removed with no trace.
**Fix (P4 roadmap):** hash-chained rows (`prev_hash`/`row_hash`), DELETE gated behind an exception; borrow ICO's govern/audit-chain from `intentional-cognition-os`.

### 2.6 API has no auth / open CORS / no tenant boundary  — **exposure**
`api/server.py`: `allow_origins=["*"]` (`:24`), no auth on any endpoint, and any caller can pass any `workspace_id` (`:82`, `:142`) — cross-workspace read/write with no boundary.
**Fix (P4 roadmap):** API auth + real workspace/tenant isolation.

### 2.7 Overclaims + fabrication  — **legal/disclosure risk (fixed THIS pass — P0)**
The marketing README (`000-docs/003-DR-REFF-readme.md`) and root `README.md`/`CLAUDE.md`/`CHANGELOG.md` claim "Zero Cloud Dependencies", "air-gapped", "100% private", **HIPAA/GDPR/SOC 2 "compliant"/"ready"**, and — most dangerous — a **fabricated portfolio line**: `003-DR-REFF-readme.md:347` *"Implemented HIPAA-compliant document processing for healthcare clients."* These are false for the shipped tool, which bundles cloud providers (`requirements.txt`) and **defaults to `NEXUS_MODE=hybrid`** (cloud egress). Also fabricated: "1000+ stars", "$4,200/year savings", "100K+ documents", "50+ concurrent users".
**Fix:** delete the fabricated client line; replace "compliant"→"designed for privacy / supports local-only operation"; drop absolute "zero cloud / air-gapped" claims (keep the honest "can run fully local").

### Fake relevance score (minor, noted for P3)
`rag_pipeline.py:193` sets `relevance_score=1.0/(i+1)` — a positional placeholder, not a real similarity/rerank score. Real citation scoring lands in P3.

---

## 3) Structural drift (cleaned up in Phase 0)

| Drift | Evidence | Resolution |
|---|---|---|
| Four names for one repo | dir `local-rag-agent` / remote `iam-local-rag` / product "NEXUS" / README slug `nexus-rag` | State the canonical trio once (§0); fix the 9 `nexus-rag` URLs. |
| 3 Streamlit apps + a shim | `02-Src/{app.py, app_optimized.py, app_nexus.py}` + FastAPI | Quarantine `app.py`, `app_optimized.py`, `load_test.py`, `performance_analysis.py` → `99-Archive/`; **keep `app_nexus.py`** (the NEXUS-core shim) until the new UI proves out. |
| Two docs dirs | `01-Docs/` (2 stale dated reports) + `000-docs/` (authoritative) | Archive `01-Docs/500`, `01-Docs/501` → `99-Archive/`; `000-docs/` is the only docs home. |
| Empty package dir | `nexus/ui/` (only `__init__.py`) | Left as the P6 target for the moved UI. |
| Dangling path refs | refs to nonexistent `.directory-standards.md` / `claudes-docs/` in `000-docs/004` + `CHANGELOG.md:54` | `004` is a historical cleanup-audit record (left as history); no live guidance points at those paths. |
| No `pyproject.toml` | absent | Add PEP 621 `pyproject.toml` (ruff + mypy + pytest + coverage). |
| CI broken | `ci.yml` installs a **missing** `requirements-dev.txt` (`:21`,`:39`); `test.yml` is **also named "CI"** and runs `pytest tests/` (nonexistent dir) with `|| echo` → silent green no-op; `05-Scripts/pytest.ini` says `testpaths = tests` (wrong dir + wrong location) | Rewrite `ci.yml` to install from pyproject extras + exercise `03-Tests/`; **delete `test.yml`**; centralize pytest config in `pyproject.toml`. |
| Stale version assertion | `03-Tests/test_api.py:60` asserts `1.0.0`; server returns `1.1.0` (`server.py:18`,`:215`) | Fix the assertion to `1.1.0`. |
| Git 1↔1 divergence | local `bd init` vs remote `FUNDING.yml` | **Reconciled** 2026-07-04 (`git pull --rebase`, master pushed). |
| `RAGPipeline` monolith | one class, dense-only, no reranker/hybrid/citation-verifier | Modularize in P3. |

---

## 4) Guiding invariants (the acceptance bar — enforced in code + tests)

1. **Every cloud/model call (LLM *and* embeddings) passes through one policy gate.** No second path.
2. **LOCAL mode makes zero external calls** — incl. embeddings; fail-closed.
3. **Every answer is cited or explicitly says evidence is insufficient.**
4. **Every query can emit a privacy receipt** (provider/model, chars/tokens out, chunk ids+hashes, redactions, policy pass/fail, local-vs-cloud).
5. **Retrieved document text is untrusted data, never instructions.**
6. **No secret in code; no key in logs; privacy never silently degraded.**
7. **Typed, tested, small coherent commits.**

---

## 5) Gap → phase map

| Phase | Theme | This pass? | Beads |
|---|---|---|---|
| **P0** | Audit + task plan + safe hygiene (git reconcile, naming, CI/tooling repair, overclaim/fabrication cleanup, legacy quarantine) | ✅ done | `local-6p0.1` `.2` `.6` `.7` |
| **P1-2** | Dangerous-bug fixes + provider correctness (embedding abstraction, one mode-aware policy gate, provider profiles/fallback/health, new provider paths, targeted tests) | ✅ done | `local-6p0.3` `.4` `.5` `.8` |
| **P3** | RAG modularization (stage interfaces under `nexus/retrieval` + `nexus/ingestion`; hybrid dense+BM25+RRF, MMR, rerank; **qmd optional backend**, Chroma fallback; real citations; insufficient-evidence refusal; answer modes; multi-format ingestion) | roadmap | `local-6p0.9` |
| **P4** | Trust moat (hash-chained ledger borrowing **ICO** govern/audit; per-query privacy receipt; injection hardening; groundedness/citation-coverage verifier; API auth + tenant boundary) | roadmap | `local-6p0.10` |
| **P5** | Evals (`nexus/evals/`: recall@k, citation coverage, groundedness, privacy-leak sentinel, injection, provider parity, latency) | roadmap | `local-6p0.11` |
| **P6** | API/UI/CLI (full endpoint set, Streamlit **privacy meter**, `nexus` CLI, optional MCP layer) | roadmap | `local-6p0.12` |
| **P7** | Docs + AAR (repositioned docs set, implementation AAR, competitive review) | roadmap | `local-6p0.13` |

**Reuse decisions (do not rebuild):** optional **qmd** (hybrid BM25+vector+rerank, already v2.0.1) as the `Retriever`/`VectorStore` backend, Chroma as the zero-dependency default; **ICO**'s hash-chained govern/audit for the tamper-evident ledger. Intent NEXUS ships **standalone** (zero-brain works) — no hard tailnet/brain dependency — positioning it as the BYOK/portable/policy front-end to the governed local knowledge stack. **SDK strategy:** thin per-provider adapters behind our own ABCs; **no agent-SDK in core** (Claude Agent SDK / Vercel AI SDK / OpenAI Agents SDK are provider-flavored lock-in — revisited only for the optional MCP/tool layer). **iOS = roadmap client** on the FastAPI (no local iOS repo exists today).

---

## 6) Verification anchors

- **P0:** git reconciled + clean; `ruff`/`mypy` run; `pytest -c pyproject.toml 03-Tests` green (incl. fixed version assertion); CI workflows valid (`actionlint`); no HIPAA/GDPR/fabricated-client strings remain; this doc filed + indexed.
- **P1-2:** `NEXUS_EMBED_PROVIDER=openai` indexes+queries with no `AttributeError`; LOCAL mode makes **zero** network calls (network-blocked stub) incl. embeddings; a sentinel secret in a chunk is **blocked** before any LLM *or* embedding cloud call; provider fallback selects the next provider on failure.

---

*This audit is the baseline for beads epic `local-6p0` ("Refactor NEXUS into a local-first BYOK document-intelligence platform"), the "revive" answer to the dormant decision epic `local-3py`.*
