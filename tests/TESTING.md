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
| `coverage.line` | 65% (unit gate; current ~69%) | CI `test` job `--cov-fail-under=65` (blocking) |
| `crap.prod` | 30 | advisory — CI `harness` job runs `audit-harness crap` with radon on PATH (truthful). ⚠ currently FAILS (avg 10.38, max 272); reduction tracked in epic `local-s9e` PR2 (provider tests raise coverage → drop CRAP). |
| `crap.test` | 15 | advisory |
| Mutation kill-rate | baseline (no floor yet) | CI `mutation` job (advisory). Targets in `setup.cfg [mutmut]`: `citation_verifier` + `ledger`. Baseline citation_verifier 10/20 killed. Floor set + `policy.py` added once PR2 lands its regex tests. |
| Ruff | 0 errors | CI `lint` job (blocking) |
| Mypy | advisory | CI `lint` job (`continue-on-error`) |
| Test-bias (smoke-only) | ≤5 / 100 tests target | CI `harness` job (advisory). Currently 14 (~9.4/100) — reduced in PR3. |
| Escape-scan | REFUSE=block | pre-commit `--staged` (blocking); CI PR-diff (advisory until baseline clean) |

Coverage is a **ratchet**: raise the floor as coverage rises; never lower it to
pass a PR (escape-scan REFUSES a lowered floor).

> **⚠ Gate-integrity note (000-docs/009 #3):** `audit-harness crap` returns
> `pass:true` / exit 0 when radon is not importable — a fail-**open** degrade
> that can show a false green. Every job that runs it installs the `[dev]` extra
> (which pins `radon>=6.0`) so the score is always computed for real. Filed as an
> upstream harness bug; do not rely on the CRAP gate in an environment without radon.

## Layers (7-layer taxonomy)

| Layer | Status | Notes |
|---|---|---|
| L1 git hooks & CI | partial | CI (lint/test/harness/integration) + `.pre-commit-config.yaml` present; run `pre-commit install` locally |
| L2 static & lint | installed | ruff (blocking) + mypy (advisory) |
| L3 unit | installed | ~130 unit tests; PolicyEngine + provider + ledger + privacy-gate. Mutation gate (mutmut) added 2026-07-05 — advisory baseline. |
| L4 integration | installed | `test_api` + `test_integration` (marker `integration`; needs Ollama). ⚠ CI job is `continue-on-error` — a mocked-provider blocking variant lands in PR3. |
| L5 system (perf/sec/a11y) | waived (early stage) | security control = PolicyEngine + secret-scan; dedicated SAST = roadmap P5 |
| L6 E2E / BDD | waived (early stage) | Gherkin/E2E deferred; optional `features/` acceptance layer for the 7 invariants tracked in epic `local-s9e` PR4 |
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

- **Date:** 2026-07-05 (specialist field-team audit — `000-docs/009-TQ-AUDT`)
- **Grade:** B (disciplined suite; 26 verified findings being remediated under epic `local-s9e`)
- **Unit coverage:** ~69% (floor raised 55 → 65)
- **CRAP:** FAILS on real radon (avg 10.38, max 272) — reduction via PR2 provider coverage
- **Mutation:** gate installed (advisory); citation_verifier baseline 10/20 killed
- **Test-bias:** 14 smoke-only (~9.4/100) — reduced in PR3
- **Escape-scan:** clean (baseline)

### Prior audit

- **Date:** 2026-07-04 · Grade B− · unit coverage 60% (floor 55) · escape-scan clean
