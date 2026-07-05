"""
Architecture guard (audit 009 #23) for acceptance invariant #1: every outbound
LLM/embedding call goes through the single PolicyEngine gate in rag_pipeline.py
(after `policy.enforce`). This static AST check fails if any OTHER nexus module
invokes a provider's `generate` / `generate_with_messages` / `embed_documents` /
`embed_query` — i.e. a second egress path that would bypass the gate.

It is a regression tripwire: current behavior is correct and functionally tested
(test_policy.py mode matrix + test_privacy_gate.py pipeline blocks), but nothing
stopped a future edit from adding an ungated call. Now adding one is a deliberate,
reviewed act (extend the allowlist) rather than a silent bypass.
"""
import ast
import os

OUTBOUND_METHODS = {"generate", "generate_with_messages", "embed_documents", "embed_query"}

# Suffix-matched files allowed to call a provider's outbound methods.
ALLOWLIST_FILE_SUFFIXES = (
    "nexus/core/rag_pipeline.py",  # THE gate — calls happen after policy.enforce
    "nexus/retrieval/embedding_adapter.py",  # ABC -> langchain embedding shim
    "nexus/evals/fakes.py",  # eval-harness provider double: FakeLLM self-delegates
    #                          generate_with_messages() -> generate(), like the real
    #                          adapters; it's a test stand-in, not a production egress path.
)
# Any file under these dirs is allowed (the adapters implement the methods and
# self-delegate: generate() -> generate_with_messages(); embed_query() -> embed_documents()).
ALLOWLIST_DIR_FRAGMENTS = ("/nexus/core/providers/",)

_NEXUS_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nexus"
)


def _nexus_py_files():
    for dirpath, _dirs, files in os.walk(_NEXUS_ROOT):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def _is_allowed(path):
    norm = path.replace(os.sep, "/")
    if any(norm.endswith(s) for s in ALLOWLIST_FILE_SUFFIXES):
        return True
    return any(frag in norm for frag in ALLOWLIST_DIR_FRAGMENTS)


def test_no_ungated_outbound_provider_calls():
    offenders = []
    for path in _nexus_py_files():
        if _is_allowed(path):
            continue
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in OUTBOUND_METHODS
            ):
                offenders.append(
                    f"{os.path.relpath(path, os.path.dirname(_NEXUS_ROOT))}:{node.lineno} "
                    f".{node.func.attr}()"
                )

    assert not offenders, (
        "Outbound provider call(s) found outside the single policy gate. Invariant #1 "
        "requires ALL LLM/embedding egress through nexus/core/rag_pipeline.py after "
        "policy.enforce. If this call is intentional and gated, add its file to the "
        "allowlist in this test:\n  " + "\n  ".join(offenders)
    )


def test_guard_actually_scans_something():
    # Fail loud if the walk finds no files (a broken path would make the guard vacuous).
    files = list(_nexus_py_files())
    assert len(files) > 10, f"expected the nexus package, found {len(files)} files"
