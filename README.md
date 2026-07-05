# Intent NEXUS — Local-first BYOK Document Intelligence

**Local-first BYOK document intelligence with verifiable citations, privacy
receipts, provider portability, and policy-bounded cloud acceleration.**

> **Identity:** one product, three names — product **Intent NEXUS** (NEXUS under
> the Intent Solutions house brand) · local directory `local-rag-agent` · GitHub
> remote [`jeremylongshore/iam-local-rag`](https://github.com/jeremylongshore/iam-local-rag).

## What it is

NEXUS turns your documents into a queryable knowledge base you control. It runs
**local-first** (Ollama + Chroma, no keys, nothing leaves the machine) and lets
you **bring your own** cloud model (Anthropic, OpenAI, Vertex, or any
OpenAI-compatible endpoint) **only when you choose to** — with every outbound
call passing through one policy gate.

> Honest scope: NEXUS *can* run fully local (air-gapped), but it also ships cloud
> provider adapters and defaults to `hybrid`. It is **designed for privacy and
> supports local-only operation** — it is not a compliance certification and
> makes no HIPAA/GDPR/SOC 2 claim.

## The trust layer (the point)

Not "a shinier chatbot" — the moat is verifiable trust, enforced in code and
measured on every run:

- **One policy gate on every outbound call** (LLM *and* embeddings). `local` mode
  makes **zero** external calls, fail-closed. `hybrid` forces local embeddings and
  sends only redacted, capped snippets. **Secrets in your corpus are blocked
  before any cloud call.**
- **Verifiable citations + refusal.** Real relevance scores; the pipeline **refuses
  in code** ("insufficient evidence") rather than guessing.
- **Privacy receipt per query** — provider/model, chars/tokens out, chunk ids +
  hashes, redactions, local-vs-cloud, policy pass/fail.
- **Tamper-evident audit ledger** — hash-chained; `nexus audit verify` proves it.
- **Untrusted-data handling** — retrieved text is data, never instructions; an
  injection scrubber neutralizes common override phrases (defense-in-depth).
- **It measures itself** — a built-in eval harness scores recall, citation
  coverage, groundedness, refusal, privacy-leak, and injection resistance.

## Modes

| Mode | Embeddings | LLM | Egress |
|---|---|---|---|
| `local` (fully private) | Ollama | Ollama | none (enforced) |
| `hybrid` (default) | local (forced) | cloud BYOK | redacted snippets only |
| `cloud` | cloud | cloud | explicit |

## Quick start (the `nexus` CLI)

```bash
git clone https://github.com/jeremylongshore/iam-local-rag.git
cd iam-local-rag
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,ui]'

# Local-only path (no keys) — small, fast models:
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen2.5:0.5b        # generation (~400MB)
ollama pull nomic-embed-text    # embeddings  (~274MB)
export NEXUS_MODE=local OLLAMA_MODEL=qwen2.5:0.5b OLLAMA_EMBED_MODEL=nomic-embed-text

nexus index 000-docs/*.md               # index your documents (path-confined to cwd)
nexus ask "What does NEXUS enforce?"    # grounded answer + sources + privacy receipt
nexus policy "email a@b.com key sk-..."  # preview redactions/secret-block — sends nothing
nexus providers                          # provider config + availability
nexus eval                               # run the offline eval suite
nexus audit verify                       # verify the tamper-evident ledger
```

Also available: **FastAPI** (`uvicorn nexus.api.server:app` — set `NEXUS_API_KEY`
to require auth) and a **Streamlit** UI (`streamlit run 02-Src/app_nexus.py`).

BYOK: copy `.env.example` to `.env` and set `NEXUS_LLM_PROVIDER` + the relevant
key. Options include `NEXUS_EMBED_PROVIDER`, `OPENAI_COMPATIBLE_BASE_URL`
(OpenRouter / Together / vLLM), `NEXUS_LLM_FALLBACK`, and `NEXUS_RETRIEVER=qmd`.

## Technology

- **Core package:** `nexus/` — `core/` (config, models, policy, router, ledger,
  pipeline, providers), `retrieval/` (Chroma + qmd backends, citation verifier),
  `evals/` (harness + metrics), `api/` (FastAPI), `cli.py`.
- **Retrieval:** Chroma dense (default) or the homegrown **qmd** hybrid
  (BM25 + vector + rerank) engine via `NEXUS_RETRIEVER=qmd`.
- **LLM runtime:** Ollama (local; dedicated `OLLAMA_EMBED_MODEL`) + BYOK cloud
  adapters (lazily imported — `import nexus` pulls no cloud SDK).
- **Python:** 3.11+.

## Documentation

All docs live in **`000-docs/`**. Start with:

- `000-docs/008-AA-AACR-implementation-aar.md` — what was built (P0–P6) + residual risks.
- `000-docs/007-AA-AUDR-architecture-audit.md` — the baseline audit + roadmap.
- `000-docs/000-INDEX.md` — the document index.

## Support

- Issues: <https://github.com/jeremylongshore/iam-local-rag/issues>

---

Built by Intent Solutions.
