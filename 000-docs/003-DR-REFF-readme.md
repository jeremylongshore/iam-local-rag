# Intent NEXUS — README Reference

**Type:** Documentation & Reference (DR-REFF)
**Status:** Honest reference for the local-first BYOK platform. Supersedes the
prior marketing README (which carried fabricated metrics, a fabricated
healthcare-client line, and HIPAA/GDPR/SOC 2 "compliance" claims — all removed
2026-07-04 per the P0 overclaim cleanup; see `007-AA-AUDR-architecture-audit.md`).

> **Identity:** product **Intent NEXUS** · local dir `local-rag-agent` · GitHub
> remote `jeremylongshore/iam-local-rag`.

---

## What NEXUS is

A local-first / hybrid / cloud-BYOK document-intelligence platform. You point it
at your documents and query them; it runs fully local by default and lets you
bring your own cloud model only when you choose to, with every outbound call
passing through one policy gate.

The moat is the trust layer: **verifiable citations, privacy receipts, provider
portability, and a policy-bounded outbound path** — not a bigger chatbot.

### Honest scope

NEXUS *can* run fully local (air-gapped) in LOCAL mode. It also ships cloud
provider adapters (Anthropic, OpenAI, Vertex, any OpenAI-compatible endpoint) and
**defaults to `hybrid`**. It is **designed for privacy and supports local-only
operation** — it is **not** a compliance certification and makes **no** HIPAA /
GDPR / SOC 2 claim, and it has not been "deployed for healthcare clients."

## Modes

| Mode | Embeddings | LLM | Egress |
|---|---|---|---|
| `local` | Ollama (local) | Ollama (local) | none — enforced, fail-closed |
| `hybrid` (default) | local (forced) | cloud BYOK | redacted, capped snippets only |
| `cloud` | cloud | cloud | explicit |

In every mode, secrets detected in outbound content are blocked before any
external call, and retrieved document text is treated as untrusted data.

## Quick start

```bash
git clone https://github.com/jeremylongshore/iam-local-rag.git
cd iam-local-rag
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,ui]'

# Local-only path (no keys):
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3

streamlit run 02-Src/app_nexus.py       # UI
# or:  uvicorn nexus.api.server:app --reload   # API
```

## Configuration (env / `.env`)

| Variable | Purpose |
|---|---|
| `NEXUS_MODE` | `local` \| `hybrid` \| `cloud` (default `hybrid`) |
| `NEXUS_LLM_PROVIDER` | `ollama` \| `anthropic` \| `openai` \| `vertex` \| `openai_compatible` |
| `NEXUS_EMBED_PROVIDER` | `ollama` \| `openai` \| `vertex` (forced local in local/hybrid) |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_CLOUD_PROJECT` | BYOK credentials |
| `OPENAI_COMPATIBLE_BASE_URL` / `_MODEL` / `_IS_LOCAL` | OpenRouter / Together / vLLM / LM Studio |
| `OPENAI_USE_RESPONSES_API` | use the OpenAI Responses API path |
| `NEXUS_LLM_FALLBACK` | comma-separated fallback providers (Ollama is the final emergency) |
| `HYBRID_SAFE_MODE` / `MAX_SNIPPET_LENGTH` | snippet capping controls |

See `.env.example` for the full list.

## Technology

- **Core package:** `nexus/` (config, models, policy, router, ledger, pipeline, providers, api).
- **Retrieval:** LangChain + ChromaDB (Chroma default; qmd hybrid+rerank backend = roadmap).
- **LLM runtime:** Ollama (local) + BYOK cloud adapters (lazily imported; `import nexus` pulls no cloud SDK).
- **UI/API:** Streamlit (`02-Src/app_nexus.py`) + FastAPI (`nexus/api/server.py`).
- **Python:** 3.11+.

## Where to go next

- `000-docs/007-AA-AUDR-architecture-audit.md` — architecture audit + P0–P7 roadmap.
- `000-docs/000-INDEX.md` — the document index.
- Root `README.md` — the public-facing summary.
- Backlog: `bd ready` (refactor epic + roadmap beads).

---

Built by Intent Solutions.
