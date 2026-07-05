# Release v1.1.6

**Release Date**: 2026-07-05

## Changes since v1.1.5

- chore: release v1.1.6 [skip ci] (1f3f4ba)
- P7: reposition docs + implementation AAR (P0-P6) (#11) (da016cf)

---

# Release v1.1.5

**Release Date**: 2026-07-05

## Changes since v1.1.4

- chore: release v1.1.5 [skip ci] (e2a118a)
- P6 (part 1): the nexus CLI (index/ask/policy/eval/audit) with agent-safe guardrails (#10) (6852cbb)

---

# Release v1.1.4

**Release Date**: 2026-07-05

## Changes since v1.1.3

- chore: release v1.1.4 [skip ci] (d289b66)
- P5: nexus/evals harness + P4b prompt-injection hardening (#9) (5542829)

---

# Release v1.1.3

**Release Date**: 2026-07-04

## Changes since v1.1.2

- chore: release v1.1.3 [skip ci] (af03dea)
- P4a: trust moat — tamper-evident hash-chained ledger + API auth + CORS lockdown (#8) (04be93e)

---

# Release v1.1.2

**Release Date**: 2026-07-04

## Changes since v1.1.1

- chore: release v1.1.2 [skip ci] (2e85926)
- P3: modular retrieval + real qmd hybrid backend + small-model defaults (#7) (ba119cc)

---

# Release v1.1.1

**Release Date**: 2026-07-04

## Changes since v1.1.0

- chore: release v1.1.1 [skip ci] (8df9321)
- Refactor NEXUS into a local-first BYOK document-intelligence platform (Phase 0 + dangerous-bug fixes) (#6) (c345075)
- chore(beads): reconcile working state and stop tracking runtime locks (506b9bf)
- bd init: initialize beads issue tracking (bb58789)
- chore: update FUNDING.yml with GitHub Sponsors + Buy Me a Coffee (5fcd259)
- Add proprietary license - All Rights Reserved (2c5fde3)
- docs: Add v1.1.0 release report (1bfd8af)

---

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2024-12-22

### 🚀 Major Features

**Hybrid Cloud RAG Platform** - Complete transformation from local-only to multi-provider hybrid cloud architecture.

### Added

#### Phase 2: Cloud Provider Integration
- **ProviderRouter**: Intelligent provider selection with mode-based constraints (LOCAL/HYBRID/CLOUD)
- **PolicyRedactor**: Hybrid safety enforcement - documents stay local, only snippets sent to cloud
- **Anthropic Claude Provider**: Official SDK integration with Claude 3.5 Sonnet support
- **OpenAI Provider**: GPT-4 + text-embedding-ada-002 (1536-dim) with batch processing
- **Google Vertex AI Provider**: Gemini 1.5 Pro + textembedding-gecko (768-dim) with multi-region support

#### Phase 3: Team Collaboration
- **SQLite Run Ledger**: Complete audit trail for all index/query operations
  - Tracks document hashes, excerpt hashes, provider usage
  - Workspace-level statistics and analytics
  - Audit trail designed for privacy review (not a compliance certification)
- **Workspace REST API**: Multi-tenant isolation
  - `GET /workspaces` - List all workspaces with stats
  - `POST /workspaces` - Create new workspace
  - `GET /runs` - Query audit trail with filters
  - `GET /runs/{run_id}` - Get specific run details

#### Phase 4: Quality & Usability
- **75+ Automated Tests**: Comprehensive test coverage
  - Unit tests (router, policy, ledger)
  - Integration tests (full RAG workflows)
  - API tests (FastAPI endpoints)
- **Streamlit UI** (`app_nexus.py`): Enterprise-grade interface
  - 4 tabs: Index, Query, Analytics, Run Ledger
  - Multi-provider configuration
  - Hybrid safety controls
  - Real-time metrics dashboard
- **CI/CD Pipeline**: Automated testing on all pushes/PRs

### Changed
- Reorganized project structure to comply with MASTER DIRECTORY STANDARDS (2025-10-06)
- Moved all source code to `02-Src/`
- Moved all tests to `03-Tests/`
- Moved scripts to `05-Scripts/`
- Created standardized directory structure (01-Docs, 02-Src, 03-Tests, etc.)
- Added `.directory-standards.md` reference file
- Updated README.md and created CLAUDE.md with directory standards references
- Removed legacy empty directories (archive, completed-docs, docs, documents, working-mds, professional-templates)
- Enhanced RAGPipeline with ledger integration and policy enforcement

### Security
- **Hybrid Safe Mode**: Documents never leave local environment
- **Snippet Truncation**: Configurable MAX_SNIPPET_LENGTH (default 4000 chars)
- **Excerpt Hashing**: Pre-truncation hashes for audit verification
- **Payload Validation**: Outbound content validation before cloud transmission

### Documentation
- Complete upgrade guide: `01-Docs/500-upgrade-summary-phases-2-4.md`
- Architecture diagrams and data flow illustrations
- Configuration reference with all env vars
- Migration guide from local-only to hybrid
- Security and compliance documentation

### Performance
- Multi-provider support maintains sub-2s query latency
- Workspace isolation with separate vector stores
- Batch processing for embeddings (100-250 per batch)
- Exponential backoff retry logic for cloud providers

### Compatibility
- ✅ **Zero breaking changes** - local-only mode still works
- ✅ **Backward compatible** - existing APIs unchanged
- ✅ **Optional cloud** - defaults to LOCAL mode if no API keys

### Contributors
- Jeremy Longshore (Intent Solutions)

## [1.0.0] - 2024-09-16

### Added
- Initial release of NEXUS Local RAG AI Agent
- Streamlit web interface for document Q&A
- Ollama integration for local LLM inference
- ChromaDB vector database for semantic search
- LangChain RAG pipeline orchestration
- Multi-format document support (PDF, TXT, MD, DOCX, HTML)
- Performance optimization features (caching, parallel processing)
- One-line installer script
- Comprehensive documentation and README
- Test suite with pytest
- GitHub Actions CI/CD pipeline

### Features
- Local-first processing; can run fully offline in LOCAL mode
- Optional BYOK cloud acceleration (hybrid/cloud modes)
- Designed for privacy; supports local-only operation
- Real-time performance metrics

---

**Note**: This changelog was created as part of directory standardization on 2025-10-06. Previous changes may not be fully documented.
