# 99-Archive

Quarantined legacy artifacts — kept for history, not part of the live product.

Archived 2026-07-04 during the local-first BYOK refactor (beads epic
`local-6p0`; see `000-docs/007-AA-AUDR-architecture-audit.md`):

| File | Was | Why archived |
|---|---|---|
| `app.py` | original Streamlit app (`02-Src/`) | superseded by the NEXUS-core shim `02-Src/app_nexus.py` |
| `app_optimized.py` | caching variant of the app | duplicate legacy app |
| `load_test.py` | ad-hoc load test | not part of the test suite |
| `performance_analysis.py` | ad-hoc perf script | not part of the test suite |
| `500-upgrade-summary-phases-2-4.md` | dated report (retired `01-Docs/`) | historical; compliance claims neutralized |
| `501-REPT-nexus-release-v1.1.0.md` | dated release report (retired `01-Docs/`) | historical; compliance claims neutralized |

The current UI is `02-Src/app_nexus.py` (kept until `nexus/ui/` replaces it in
roadmap P6). All live documentation lives in `000-docs/`.
