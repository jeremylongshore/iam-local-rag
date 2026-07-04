# TESTING.md — Intent NEXUS

Test policy for `iam-local-rag`. Engineer-owned policy sections are the source of
truth; the audit harness (`@intentsolutions` / `intent-audit-harness`) enforces
them in-repo (never via `~/.claude` paths).

## Classification

- **Repo type:** service/api + library (Python; FastAPI server + `nexus/` core package)
- **Runtime:** Python 3.11+
- **Frameworks:** pytest (unit + integration marker), ruff, mypy
- **Compliance overlay:** none

## Thresholds (policy — engineer-owned)

| Gate | Floor | Enforced |
|---|---|---|
| `coverage.line` | 55% (unit gate; current 60%) | CI `test` job `--cov-fail-under=55` (blocking) |
| `crap.prod` | 30 | advisory (needs radon; degraded-pass otherwise) |
| `crap.test` | 15 | advisory |
| Ruff | 0 errors | CI `lint` job (blocking) |
| Mypy | advisory | CI `lint` job (`continue-on-error`) |
| Test-bias (smoke-only) | informational | CI `harness` job (advisory) |
| Escape-scan | REFUSE=block | pre-commit `--staged` (blocking); CI PR-diff (advisory until baseline clean) |

Coverage is a **ratchet**: raise the floor as coverage rises; never lower it to
pass a PR (escape-scan REFUSES a lowered floor).

## Layers (7-layer taxonomy)

| Layer | Status | Notes |
|---|---|---|
| L1 git hooks & CI | partial | CI (lint/test/harness/integration) + `.pre-commit-config.yaml` present; run `pre-commit install` locally |
| L2 static & lint | installed | ruff (blocking) + mypy (advisory) |
| L3 unit | installed | 65 unit tests; PolicyEngine + provider + ledger + privacy-gate |
| L4 integration | installed | `test_api` + `test_integration` (marker `integration`; needs Ollama) |
| L5 system (perf/sec/a11y) | waived (early stage) | security control = PolicyEngine + secret-scan; dedicated SAST = roadmap P5 |
| L6 E2E / BDD | waived (early stage) | Gherkin/E2E deferred to roadmap P5/P6 |
| L7 acceptance / UAT | waived (early stage) | product pre-1.0 |

## Installed gates

- `pyproject.toml`: ruff + mypy + pytest + coverage config; `dev` extra includes
  `intent-audit-harness` + `radon`.
- CI (`.github/workflows/ci.yml`): `lint`, `test` (3.11/3.12, coverage floor),
  `harness` (verify + bias + escape-scan), `integration` (Ollama, non-blocking).
- pre-commit: ruff, ruff-format, standard hooks, `detect-private-key`,
  audit-harness escape-scan.
- Hash manifest: `.harness-hash` pins policy files.

## Waived layers (engineer policy)

L5 (system: perf/sec/a11y/chaos), L6 (E2E/BDD), L7 (UAT) — waived at this stage;
tracked as roadmap beads (P5 evals incl. injection/privacy-leak corpus; P6 UI/CLI).

## Traceability

RTM / personas / journeys not yet generated (pre-1.0). The acceptance invariants
in `CLAUDE.md` + `000-docs/007-AA-AUDR-architecture-audit.md` are the current
requirement anchors; each is covered by a `test_privacy_gate.py` / `test_policy.py`
test. Formal RTM = roadmap.

## Last audit

- **Date:** 2026-07-04
- **Grade:** B− (solid L1–L4; L5–L7 waived early-stage)
- **Unit coverage:** 60% (floor 55)
- **Escape-scan:** clean (baseline)
