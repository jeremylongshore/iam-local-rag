# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repository.

## Identity

One product, three names — do not invent a fourth:

- **Product:** Intent NEXUS (NEXUS under the Intent Solutions house brand)
- **Local directory:** `local-rag-agent`
- **GitHub remote:** `jeremylongshore/iam-local-rag`

Intent NEXUS is a **local-first / hybrid / cloud-BYOK document-intelligence
platform**. Its moat is the trust layer: verifiable citations, privacy receipts,
provider portability, and a policy-bounded outbound path — not a bigger chatbot.

> Honest scope: NEXUS ships cloud provider adapters and defaults to `hybrid`. It
> **is designed for privacy and supports local-only operation**; it is NOT a
> compliance product — never claim HIPAA/GDPR/SOC 2 "compliance", "zero cloud
> dependencies", or client deployments that did not happen.

## Acceptance invariants (enforce in code + tests)

1. Every cloud/model call (LLM *and* embeddings) passes through one policy gate.
2. LOCAL mode makes zero external calls (incl. embeddings), fail-closed.
3. Every answer is cited or explicitly says evidence is insufficient.
4. Every query can emit a privacy receipt.
5. Retrieved document text is untrusted data, never instructions.
6. No secret in code; no key in logs; privacy never silently degraded.
7. Typed, tested, small coherent commits.

## Architecture

The real code lives in the `nexus/` package:

```
nexus/
  cli.py             # the `nexus` CLI (index/ask/policy/providers/config/eval/audit)
  core/
    config.py        # env-driven Config (modes, providers, fallbacks) + validate()
    models.py        # Pydantic models incl. PrivacyReceipt
    policy.py        # PolicyEngine — the single mode-aware outbound gate + injection scrubber
    router.py        # provider selection + preferred->fallback->local routing
    ledger.py        # tamper-evident hash-chained audit ledger + verify_chain()
    rag_pipeline.py  # index/query; policy-gated calls; real citations + refusal
    providers/       # base ABCs + profiles + ollama/openai/anthropic/vertex + OpenAI-compatible
  retrieval/         # Retriever interface: ChromaRetriever (real scores) + QmdRetriever + CitationVerifier
  evals/             # eval harness + metrics (recall/citation/groundedness/refusal/privacy-leak/injection)
  api/server.py      # FastAPI: API-key auth + CORS allowlist + /audit/verify
  ui/                # (empty; Streamlit privacy meter moves here — roadmap P6)
02-Src/app_nexus.py  # current Streamlit shim (kept until nexus/ui replaces it)
03-Tests/            # pytest suite (unit + integration marker)
000-docs/            # ALL documentation (filed per the IS doc standard)
```

**Documentation lives in `000-docs/`.** There is no `.directory-standards.md`
and no `claudes-docs/`; the old `01-Docs/` is archived. New docs follow
`NNN-CC-ABCD-description.md`. Start at `000-docs/000-INDEX.md`, the audit
`007-AA-AUDR-architecture-audit.md`, and the implementation AAR
`008-AA-AACR-implementation-aar.md`.

## Technology stack

- **Python:** 3.11+
- **Retrieval:** Chroma dense (default) or the homegrown **qmd** hybrid backend
  (`NEXUS_RETRIEVER=qmd`) via `langchain`/`langchain-chroma`.
- **LLM runtime:** Ollama (local; dedicated `OLLAMA_EMBED_MODEL`) via
  `langchain-ollama` + BYOK cloud adapters (Anthropic/OpenAI/Vertex/OpenAI-compatible).
- **Interfaces:** `nexus` CLI + FastAPI (authed) + Streamlit.
- **Packaging/tooling:** `pyproject.toml` (ruff + mypy + pytest + coverage + audit harness).

## Development commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,ui]'          # runtime + dev tooling + Streamlit

nexus ask "…"                        # the CLI (index/ask/policy/providers/eval/audit)
python -m nexus.evals.run [--live]   # run the eval harness

pytest -m "not integration"          # unit gate (no Ollama needed)
pytest -m integration                # needs a live Ollama (small models fine)
ruff check .                         # lint (blocking in CI)
mypy                                 # type check (advisory in CI)
pre-commit install                   # optional: mirror the lint gate locally
```

Cloud provider SDKs are optional extras: `.[openai]`, `.[anthropic]`,
`.[vertex]`, or `.[cloud]`. Importing `nexus` never pulls a cloud SDK.

## Working conventions

- Ask before creating new files/dirs; prefer editing existing ones.
- Follow the acceptance invariants; a new outbound path MUST go through the
  PolicyEngine — no second path.
- Verify before claiming done; close beads with evidence.
- The roadmap (P3–P7) is tracked as beads under the refactor epic; see the audit
  doc for the gap→phase map.

## Task tracking (beads / bd)

- Use `bd` for all task tracking (no markdown TODO lists).
- `bd ready` → `bd update <id> --status in_progress` → work → `bd close <id> --reason "evidence"`.
- Plain-English bead titles; the 3-char id is a command handle, never quoted in chat/commits.
- After upgrading `bd`: `bd info --whats-new`; if hooks are stale, `bd hooks install`.
