# TEST_AUDIT.md — Intent NEXUS (iam-local-rag)

**Date:** 2026-07-04 · **Skill:** `/audit-tests` → `/implement-tests`
**Grade:** **B− (78/100)** — solid L1–L4 foundation; L5–L7 waived (early stage).

## Classification

- **Type:** service/api + library (Python 3.11+; FastAPI `nexus/api` + `nexus/` core package)
- **Frameworks:** pytest (unit + `integration` marker), ruff, mypy
- **Harness:** `intent-audit-harness` 1.2.3 installed in-repo (`.[dev]`)

## Per-layer map

| Layer | Presence | Config | Enforcement |
|---|---|---|---|
| L1 hooks & CI | partial | `.pre-commit-config.yaml` + `ci.yml` (lint/test/harness/integration) | CI blocking; git hooks require local `pre-commit install` |
| L2 static/lint | ✅ | ruff + mypy in `pyproject.toml` | ruff blocking, mypy advisory |
| L3 unit | ✅ | 65 tests; coverage 60% | `--cov-fail-under=55` (blocking) |
| L4 integration | ✅ | `test_api` + `test_integration` (Ollama) | CI job (non-blocking; needs Ollama) |
| L5 system | ➖ waived | — | roadmap P5 (evals: injection, privacy-leak, perf) |
| L6 E2E/BDD | ➖ waived | — | roadmap P5/P6 |
| L7 UAT | ➖ waived | — | pre-1.0 |

## Deterministic gates

| Gate | Result |
|---|---|
| Coverage (unit) | **60%** (1220 stmts, 435 miss) → floor set to 55 (ratchet) |
| Ruff | clean |
| Mypy | 29 advisory (pre-existing implicit-Optional) |
| Test-bias | 15 smoke-only (`is not None`) assertions in `03-Tests` — mostly import-resolution checks; informational |
| CRAP | degraded-pass (radon added to `.[dev]`; run locally for scores) |
| Escape-scan | clean baseline |

## Gaps

**P1 (addressed this pass):**
- Harness was not installed in-repo → added `intent-audit-harness` + `radon` to `.[dev]`.
- Coverage was measured but not enforced → CI `test` job now gates at `--cov-fail-under=55`.
- No in-repo escape-scan → added to pre-commit + CI `harness` job.
- No test-policy doc → `tests/TESTING.md` created.

**P2 (deferred, tracked as roadmap beads):**
- L5 security/perf gates + injection & privacy-leak eval corpus → roadmap P5 (`local-6p0.11`).
- L6/L7 BDD/E2E/UAT → roadmap P5/P6.
- Formal RTM / personas / journeys → deferred (pre-1.0); acceptance invariants in
  `000-docs/007-AA-AUDR-architecture-audit.md` are the current requirement anchors.
- Strengthen the 15 smoke-only test assertions where a stronger check is meaningful.

## Handoff

`/implement-tests` executed the P1 fixes above (harness in-repo, coverage gate,
escape-scan wiring, TESTING.md, hash manifest). L5–L7 remain waived per
`tests/TESTING.md#Waived layers` and are tracked as roadmap beads under epic
`local-6p0`.
