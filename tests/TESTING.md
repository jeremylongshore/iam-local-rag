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
| `coverage.line` | 78% (unit gate; current ~80%) | CI `test` job `--cov-fail-under=78` (blocking) |
| `crap.prod` | 30 | advisory — CI `harness` job runs `audit-harness crap` with **radon on PATH + `coverage.json` present** (truthful). With real coverage factored in, `nexus/` blockers are 4 (all low-coverage `evals/metrics/*`); the raw "avg 10.38 / max 272" was coverage=0 scoring + the harness scanning `99-Archive/` legacy (no exclude config — upstream ask). |
| `crap.test` | 15 | advisory |
| Mutation kill-rate | baseline (no floor yet) | CI `mutation` job (advisory, `--use-coverage`). Scope in `setup.cfg [mutmut]`: PR1 `citation_verifier` (baseline 10/20) → PR3 `+ledger.py`. `policy.py` stays OUT (regex-string mutants are low-value noise); its regexes are covered by the PR2 positive + near-miss boundary tests instead. |
| Ruff | 0 errors | CI `lint` job (blocking) |
| Mypy | advisory | CI `lint` job (`continue-on-error`) |
| Test-bias (smoke-only) | ≤5 / 100 tests target | CI `harness` job (advisory). Currently 14 (~9.4/100) — reduced in PR3. |
| Escape-scan | REFUSE=block | pre-commit `--staged` (blocking); CI PR-diff (advisory until baseline clean) |

Coverage is a **ratchet**: raise the floor as coverage rises; never lower it to
pass a PR (escape-scan REFUSES a lowered floor).

### Machine-readable thresholds

`audit-harness escape-scan` reads the floors from these exact `key: value` lines
(it greps `TESTING.md` under `set -euo pipefail`, so all three MUST be present as
colon lines — a missing one silently aborts the scanner mid-run). Keep them in
sync with the human Thresholds table above and the CI gates.

```yaml
coverage.line: 78
coverage.branch: 55
# advisory baseline — no enforced kill-rate floor yet (see epic local-s9e)
mutation.kill_rate: 0
```

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
| L3 unit | installed | ~216 unit tests; PolicyEngine + provider adapters (behavioral, SDK-mocked) + ABC contract + ledger + privacy-gate + single-gate AST guard + **property/fuzz** (`test_properties.py`, hypothesis: regex totality + hash-chain determinism/injectivity). Mutation gate (mutmut) advisory. |
| L4 integration | installed | `test_api` + `test_integration` (marker `integration`; needs Ollama). A mocked-provider **blocking** variant (`test_api_mocked.py`, shared `conftest.py` fixture) covers endpoint routing/auth/errors without Ollama; two mis-asserting integration tests (redaction/truncation) now assert real behavior. |
| L5 system (perf/sec/a11y) | waived (early stage) | security control = PolicyEngine + secret-scan; dedicated SAST = roadmap P5 |
| L6 E2E / BDD | **installed (seed)** | `features/acceptance_invariants.feature` + `test_bdd_acceptance.py` (pytest-bdd) — executable Gherkin for the policy-gate, secret-block, and cited-or-refuse invariants. Runs in the unit gate; CI `harness` job gherkin-lints it. Grows toward all 7 invariants. |
| L7 acceptance / UAT | **installed (seed)** | the BDD scenarios above ARE the acceptance specs, bound to real code (not prose). |

## Installed gates

- `pyproject.toml`: ruff + mypy + pytest + coverage config; `dev` extra includes
  `intent-audit-harness` + `radon`.
- CI (`.github/workflows/ci.yml`): `lint`, `test` (3.11/3.12, coverage floor),
  `harness` (verify + bias + escape-scan), `integration` (Ollama, non-blocking).
- pre-commit: ruff, ruff-format, standard hooks, `detect-private-key`,
  audit-harness escape-scan.
- Hash manifest: `.harness-hash` pins policy files.

## Waived layers (engineer policy)

L5 (system: perf/sec/a11y/chaos) — waived at this stage (security control =
PolicyEngine + secret-scan; dedicated SAST is roadmap). L6/L7 are no longer
waived: a seed BDD acceptance layer landed 2026-07-05 (epic `local-s9e` PR4) and
grows toward all 7 invariants.

## Traceability

RTM / personas / journeys not yet generated (pre-1.0). The acceptance invariants
in `CLAUDE.md` + `000-docs/007-AA-AUDR-architecture-audit.md` are the current
requirement anchors; each is covered by a `test_privacy_gate.py` / `test_policy.py`
test. Formal RTM = roadmap.

## Last audit

- **Date:** 2026-07-05 (specialist field-team audit — `000-docs/009-TQ-AUDT`)
- **Grade:** B → A− (all 26 verified findings remediated under epic `local-s9e`; PR1-PR4 landed)
- **Unit coverage:** ~80% (216 unit tests; floor raised 55 → 65 → 75 → 78). Provider adapters 20-23% → 58-82%; server.py 60% → 71%; cli.py 72% → 90%.
- **CRAP:** with coverage.json + radon, `nexus/` blockers 43 → 4 (all low-coverage `evals/metrics/*`); "max 272" was `99-Archive/` legacy
- **Mutation:** gate installed (advisory); citation_verifier baseline 10/20 killed
- **Property/fuzz:** hypothesis over the policy regexes + ledger hash-chain (new)
- **Score bug:** ChromaRetriever out-of-[0,1] relevance scores fixed (cosine + clamp)
- **BDD:** seed L6/L7 acceptance layer (`features/*.feature`), gherkin-lint clean
- **Escape-scan:** clean; floor-lowering gate now actually enforced (PR1 fix)

### Prior audit

- **Date:** 2026-07-04 · Grade B− · unit coverage 60% (floor 55) · escape-scan clean
