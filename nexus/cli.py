"""
Intent NEXUS command-line interface.

The primary interface for a local-first tool: index your docs, ask questions,
preview the policy, run evals, and verify the audit chain — all policy-gated and
receipted, no server required.

Safety by design (defense-in-depth; a read-mostly data-plane tool):
- Read-mostly verbs; no destructive commands; no arbitrary shell (argparse only).
- `nexus index` is PATH-CONFINED to an allowlisted root (default: cwd). This
  guards the confused-deputy case where injected DOCUMENT content steers indexing
  toward sensitive files (e.g. /etc/shadow) for later exfiltration via a cloud
  query. IMPORTANT: `--allow-root` and NEXUS_ALLOWED_INDEX_ROOTS are OPERATOR
  controls on a TRUSTED channel — an agent that fully controls the argv/env can
  widen the root, so any MCP/tool wrapper MUST expose only `paths` (never
  --allow-root or the env override) to preserve the guarantee.
- Every command runs through the same PolicyEngine gate + tamper-evident ledger.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional


def _allowed_roots(extra: Optional[List[str]] = None) -> List[str]:
    env = os.getenv("NEXUS_ALLOWED_INDEX_ROOTS", "")
    roots = [r.strip() for r in env.split(",") if r.strip()]
    roots.extend(extra or [])
    if not roots:
        roots = [os.getcwd()]
    return [os.path.realpath(r) for r in roots]


def confine_paths(paths: List[str], roots: List[str]) -> List[str]:
    """Resolve each path and require it to live under an allowed root."""
    # normcase both sides so comparison holds on case-insensitive filesystems
    # (Windows/macOS); on Linux it is a no-op.
    norm_roots = [os.path.normcase(r) for r in roots]
    confined: List[str] = []
    for p in paths:
        rp = os.path.realpath(p)
        nrp = os.path.normcase(rp)
        # os.path.join(root, "") normalizes the trailing separator so a root of
        # "/" (which would make root+os.sep "//") still matches its children.
        if not any(nrp == nroot or nrp.startswith(os.path.join(nroot, "")) for nroot in norm_roots):
            raise ValueError(
                f"refusing to index {p!r}: outside allowed roots {roots}. "
                f"Extend with --allow-root or NEXUS_ALLOWED_INDEX_ROOTS."
            )
        confined.append(rp)
    return confined


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_index(args) -> int:
    # Confine BEFORE importing the pipeline, so the guardrail runs even if the
    # heavy import were to fail.
    try:
        paths = confine_paths(args.paths, _allowed_roots(args.allow_root))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    from .core.models import IndexRequest
    from .core.rag_pipeline import RAGPipeline

    pipe = RAGPipeline(workspace_id=args.workspace)
    result = pipe.index_documents(IndexRequest(paths=paths, workspace_id=args.workspace))
    if args.json:
        print(json.dumps({"files_processed": result.files_processed, "chunks": result.total_chunks}))
    else:
        print(f"indexed {result.files_processed} file(s), {result.total_chunks} chunk(s) "
              f"into workspace '{args.workspace}'")
    return 0


def cmd_ask(args) -> int:
    from .core.models import QueryRequest
    from .core.policy import PolicyViolation
    from .core.rag_pipeline import RAGPipeline

    pipe = RAGPipeline(workspace_id=args.workspace)
    try:
        resp = pipe.query(
            QueryRequest(question=args.question, workspace_id=args.workspace, max_results=args.k)
        )
    except PolicyViolation as e:
        print(f"blocked by policy: {e}", file=sys.stderr)
        return 3
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(resp.model_dump_json(indent=2))
        return 0

    print(resp.answer)
    if resp.citations:
        print("\nsources:")
        for c in resp.citations:
            print(f"  - {c.source} (score {c.relevance_score:.3f})")
    r = resp.privacy_receipt
    if r:
        print(
            f"\nprivacy receipt: {r.llm_provider} [{r.llm_destination}] · "
            f"{r.chars_sent_to_cloud} chars to cloud · "
            f"redactions={sum(x.get('count', 0) for x in (r.redactions or []))} · "
            f"policy_pass={r.policy_pass}"
        )
    return 0


def cmd_policy(args) -> int:
    """Preview what the policy would do to text — WITHOUT sending anything."""
    from .core.policy import PolicyEngine

    engine = PolicyEngine(mode=args.mode)
    secrets = engine.scan_secrets(args.text)
    _, pii = engine.redact_pii(args.text)
    _, injections = engine.scrub_injection(args.text)
    out = {
        "mode": engine.mode.value,
        "secrets_detected": secrets,
        "pii_would_redact": [{"kind": r.kind, "count": r.count} for r in pii],
        "injection_phrases_scrubbed": injections,
        "would_block_cloud": bool(secrets),
    }
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"mode: {out['mode']}")
        print(f"secrets detected: {secrets or 'none'}  (blocks cloud: {out['would_block_cloud']})")
        print(f"PII to redact: {out['pii_would_redact'] or 'none'}")
        print(f"injection phrases scrubbed: {injections}")
    return 0


def cmd_providers(args) -> int:
    from .core.router import ProviderRouter

    results = ProviderRouter.validate_configuration()
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"mode: {results['mode']}")
        print(f"llm: {results['llm_provider']} (available: {results.get('llm_available')})")
        print(f"embed: {results['embed_provider']} (available: {results.get('embed_available')})")
        for w in results.get("warnings", []):
            print(f"  warn: {w}")
        for e in results.get("errors", []):
            print(f"  error: {e}")
    # Non-zero on genuine misconfiguration (errors); a merely-unavailable local
    # provider is a warning, not a failure.
    return 0 if results.get("valid", True) else 1


def cmd_config(args) -> int:
    from .core.config import Config

    summary = Config.get_summary()
    print(json.dumps(summary, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in summary.items()))
    return 0


def cmd_eval(args) -> int:
    from .evals.run import main as eval_main

    argv = []
    if args.live:
        argv.append("--live")
    if args.json:
        argv.append("--json")
    return eval_main(argv)


def cmd_audit(args) -> int:
    from .core.ledger import RunLedger

    ledger = RunLedger()
    if args.audit_cmd == "verify":
        result = ledger.verify_chain()
        print(json.dumps(result, indent=2) if args.json else
              f"audit chain: {'OK' if result['ok'] else 'BROKEN'} ({result['total']} entries)"
              + ("" if result["ok"] else f"\nbreaks: {result['breaks']}"))
        return 0 if result["ok"] else 1
    runs = ledger.list_runs(limit=args.limit)
    print(json.dumps(runs, indent=2, default=str) if args.json else
          f"index runs: {len(runs['index_runs'])} · query runs: {len(runs['query_runs'])}")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    # --json on a shared parent so it works after any subcommand (nexus ask q --json).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")

    p = argparse.ArgumentParser(
        prog="nexus", description="Intent NEXUS — local-first BYOK document intelligence"
    )
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("index", parents=[common], help="index documents (path-confined)")
    pi.add_argument("paths", nargs="+", help="files to index")
    pi.add_argument("--workspace", default="default")
    pi.add_argument("--allow-root", action="append", default=[], help="extend allowed index roots")
    pi.set_defaults(func=cmd_index)

    pa = sub.add_parser("ask", parents=[common], help="ask a question")
    pa.add_argument("question")
    pa.add_argument("--workspace", default="default")
    pa.add_argument("-k", type=int, default=3, dest="k", help="max results")
    pa.set_defaults(func=cmd_ask)

    pp = sub.add_parser("policy", parents=[common], help="preview policy decisions for text (sends nothing)")
    pp.add_argument("text")
    pp.add_argument("--mode", default=None, choices=["local", "hybrid", "cloud"])
    pp.set_defaults(func=cmd_policy)

    pv = sub.add_parser("providers", parents=[common], help="show provider configuration + availability")
    pv.set_defaults(func=cmd_providers)

    pc = sub.add_parser("config", parents=[common], help="show the effective configuration (no secrets)")
    pc.set_defaults(func=cmd_config)

    pe = sub.add_parser("eval", parents=[common], help="run the evaluation harness")
    pe.add_argument("--live", action="store_true", help="also run metrics needing a live model")
    pe.set_defaults(func=cmd_eval)

    pu = sub.add_parser("audit", parents=[common], help="inspect the tamper-evident audit ledger")
    pu.add_argument("audit_cmd", choices=["verify", "runs"], nargs="?", default="verify")
    pu.add_argument("--limit", type=int, default=20)
    pu.set_defaults(func=cmd_audit)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
