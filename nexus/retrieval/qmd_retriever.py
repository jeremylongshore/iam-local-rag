"""
qmd retrieval backend — drives the homegrown qmd hybrid engine (BM25 + vector
+ rerank) via its CLI. This is the REAL qmd binary, not a reimplementation.

qmd indexes folders ("collections") of markdown and answers `qmd query --json`
with reranked, cited hits. NEXUS writes each chunk as a markdown file into a
per-workspace corpus, isolates qmd's index under the workspace (XDG_CACHE_HOME),
indexes + embeds it, then queries. Retrieval is fully on-host (is_local=True).

If the qmd binary is missing/broken, `QmdUnavailable` is raised so the factory
can fall back to Chroma.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import List

from ..core.providers.profiles import ProviderPrivacyProfile
from .base import IndexStats, RetrievedChunk, Retriever


class QmdUnavailable(RuntimeError):
    """Raised when the qmd binary cannot be used."""


class QmdRetriever(Retriever):
    name = "qmd"

    def __init__(self, workspace_dir: str, qmd_bin: str = "qmd", timeout: int = 300):
        self._qmd = qmd_bin
        self._timeout = timeout
        self._workspace = os.path.abspath(workspace_dir)
        self._corpus = os.path.join(self._workspace, "qmd_corpus")
        self._home = os.path.join(self._workspace, ".qmd_home")  # isolates qmd's index
        self._manifest_path = os.path.join(self._workspace, "qmd_manifest.json")
        if not self._binary_ok():
            raise QmdUnavailable(f"qmd binary '{qmd_bin}' not found or not runnable")

    # --- subprocess plumbing ---

    def _env(self) -> dict:
        env = dict(os.environ)
        # Keep NEXUS's qmd index out of the user's global ~/.cache/qmd.
        env["XDG_CACHE_HOME"] = self._home
        return env

    def _run(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [self._qmd, *args],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                env=self._env(),
                cwd=self._workspace,
                check=check,
            )
        except FileNotFoundError as e:
            raise QmdUnavailable(str(e)) from e
        except subprocess.TimeoutExpired as e:
            raise QmdUnavailable(f"qmd timed out after {self._timeout}s") from e

    def _binary_ok(self) -> bool:
        try:
            subprocess.run(
                [self._qmd, "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return True
        except Exception:
            return False

    # --- manifest (chunk file -> source metadata) ---

    def _load_manifest(self) -> dict:
        if os.path.exists(self._manifest_path):
            with open(self._manifest_path) as f:
                return json.load(f)
        return {}

    def _save_manifest(self, manifest: dict) -> None:
        with open(self._manifest_path, "w") as f:
            json.dump(manifest, f)

    # --- Retriever interface ---

    def index(self, documents: List) -> IndexStats:
        os.makedirs(self._corpus, exist_ok=True)
        manifest = self._load_manifest()
        written = 0
        for doc in documents:
            content = doc.page_content
            chash = RetrievedChunk.hash_content(content)
            fname = f"{chash[:16]}.md"
            fpath = os.path.join(self._corpus, fname)
            if not os.path.exists(fpath):
                with open(fpath, "w") as f:
                    f.write(content)
                written += 1
            manifest[fname] = {
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page"),
                "content_hash": chash,
            }
        self._save_manifest(manifest)

        # Register + (re)index + embed the corpus with qmd.
        self._run(["collection", "add", self._corpus], check=False)
        self._run(["update"], check=False)
        self._run(["embed"], check=False)
        return IndexStats(chunks_indexed=written, backend=self.name, detail="qmd collection embedded")

    def retrieve(self, query: str, k: int) -> List[RetrievedChunk]:
        result = self._run(["query", query, "--json", "-n", str(k)], check=False)
        hits = self._parse_query_json(result.stdout)
        manifest = self._load_manifest()
        chunks: List[RetrievedChunk] = []
        for hit in hits[:k]:
            content = hit.get("content") or hit.get("snippet") or hit.get("text") or ""
            path = hit.get("path") or hit.get("file") or hit.get("source") or ""
            fname = os.path.basename(path)
            meta = manifest.get(fname, {})
            chash = meta.get("content_hash") or RetrievedChunk.hash_content(content)
            score = hit.get("score", hit.get("rerank_score", 0.0))
            chunks.append(
                RetrievedChunk(
                    content=content,
                    source=meta.get("source", path or "unknown"),
                    page=meta.get("page"),
                    score=float(score) if score is not None else 0.0,
                    chunk_id=(chash or "")[:12],
                    content_hash=chash,
                    retrieval_kind="hybrid",
                    rerank_score=hit.get("rerank_score"),
                )
            )
        return chunks

    @staticmethod
    def _parse_query_json(stdout: str) -> List[dict]:
        """qmd emits noise on stderr; --json goes to stdout. Parse defensively."""
        text = (stdout or "").strip()
        if not text:
            return []
        # Find the JSON payload (array or object) even if a banner leaked in.
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                try:
                    data = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for key in ("results", "hits", "matches", "documents"):
                        if isinstance(data.get(key), list):
                            return data[key]
                    return [data]
        return []

    def exists(self) -> bool:
        return os.path.exists(self._corpus) and bool(os.listdir(self._corpus))

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="qmd", is_local=True, sends_data_offhost=False, data_region="on-host"
        )
