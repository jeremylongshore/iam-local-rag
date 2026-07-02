# Backlog Zero — Revival Manifest: local-rag-agent (NEXUS)

**Campaign:** Backlog Zero, Wave 0 (dormant-repo settle)
**Date:** 2026-07-02
**Repo:** `local-rag-agent` (remote `jeremylongshore/iam-local-rag`, default branch `master`)
**Runner:** backlog-zero mutation-runner (db triage from `.beads/issues.jsonl` snapshot, verified against the repo)
**End-state:** 4 open beads settled → only the revival epic remains open. No needs-human beads were required.

---

## Revival epic

**`local-3py` — Revive or archive NEXUS local-rag-agent: settle the dormant backlog and decide the project's future** (P2, labels `backlog-zero,revival`)

The entire open backlog was done-but-open drift: the "NEXUS Hybrid Cloud Upgrade" epic and its
three phase tasks described work that was re-tracked under a later epic ("NEXUS Phases 2-4",
10/10 children closed) and shipped as **v1.1.0 — Hybrid Cloud Upgrade** (tag `e4a0e53`,
release-report commit `1bfd8af`). Revival needs: (1) decide whether NEXUS remains a live product
line or gets archived; (2) if reviving, refresh the LangChain/ChromaDB/Ollama dependency pins and
re-verify CI; (3) settle the stray `feat/nexus-rebrand` and `chore/portfolio-upgrade` remote branches.

## Settled beads

| Bead | Title | Disposition | Evidence (one line) |
|---|---|---|---|
| local-rag-agent-v2b | NEXUS Hybrid Cloud Upgrade - Epic | Closed — done-but-open drift | Shipped end-to-end as v1.1.0 (tag `e4a0e53`; AAR `000-docs/006-AA-REPT-nexus-hybrid-cloud-team-upgrade.md`); Phases 0/1/5 closed earlier, 2/3/4 closed today; duplicate epic `local-rag-agent-0h0` fully closed 10/10 |
| local-rag-agent-v2b.3 | Phase 2: Provider Interfaces + Routing | Closed — done-but-open drift | `nexus/core/providers/{base,ollama,anthropic,openai,vertex}_provider.py`, `nexus/core/router.py` (NEXUS_MODE local/cloud/hybrid), `nexus/core/policy.py` (snippets-only); commit `487b065` et seq. |
| local-rag-agent-v2b.4 | Phase 3: Team Mode + API | Closed — done-but-open drift | `nexus/core/ledger.py` (SQLite run ledger), workspace-scoped collections in `nexus/core/rag_pipeline.py`, headless API `nexus/api/server.py` (/query, /index, /health, /workspaces, /runs) |
| local-rag-agent-v2b.5 | Phase 4: Tests + CI | Closed — done-but-open drift | `03-Tests/test_{router,policy,ledger,api,integration,smoke,streamlit_smoke,imports}.py`; commits `e4b5ec4`/`f7f2d64`/`63f29c7`; `.github/workflows/{ci,test,release}.yml` |

The mechanical duplication (v2b Phases 2–4 re-tracked as epic 0h0 with granular children, both
sets describing one shipped body of work) is why these four sat open: the work closed under 0h0
while the original v2b beads were never reconciled.

## In-flight residue (left alone)

- **Pre-existing dirty working tree (NOT committed):** `.beads/issues.jsonl` was already staged-modified before this settle (bd writes also touch it); `.beads/dolt-monitor.pid.lock` deleted (unstaged); `.beads/export-state.json` untracked.
- **Local master** carries an unpushed `bd init` commit (`df952cf`) that diverged from origin/master (which advanced with FUNDING.yml).
- **Branches:** local `chore/eod-2024-09-16` (checked out in an internal beads worktree under `.git/beads-worktrees/`), `feat/nexus-rebrand` (local + remote), remote `chore/portfolio-upgrade`.
- **Open PRs:** none.
- **in_progress beads:** none.
- **Beads backend quirk:** every `bd` invocation auto-re-imports the 19 issues from JSONL into an empty database (embedded store not persisting); harmless because `.beads/issues.jsonl` is the source of truth and was exported after every write, but worth fixing on revival.

## Needs-human digest

None. The single genuine decision — revive NEXUS as a product line vs archive it — is the
revival epic's charter (`local-3py`), not a separate needs-human bead.
