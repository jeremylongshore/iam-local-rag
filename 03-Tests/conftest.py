"""
Shared fixtures for the NEXUS test suite.

`mocked_api` gives a FastAPI TestClient wired to an isolated tmp ledger + a fake
pipeline factory, so API routing / auth / serialization tests run in the BLOCKING
unit gate with no Ollama and — critically — no real `./nexus_ledger.db` written
into the repo (000-docs/009 #6, #9). All temp state uses pytest's `tmp_path` (#26).
"""
import pytest
from fastapi.testclient import TestClient

import nexus.api.server as server
from nexus.api.server import app, get_ledger
from nexus.core.config import Config
from nexus.core.ledger import RunLedger


class _FakeRetriever:
    def __init__(self, exists: bool):
        self._exists = exists

    def exists(self) -> bool:
        return self._exists


class FakePipeline:
    """Minimal RAGPipeline stand-in for API-wiring tests (no Ollama)."""

    def __init__(self, workspace_dir, *, exists: bool = False, error: Exception = None):
        self.workspace_dir = str(workspace_dir)
        self.chroma_path = str(workspace_dir)
        self.retriever = _FakeRetriever(exists)
        self._error = error

    def query(self, request):
        if self._error:
            raise self._error
        raise AssertionError("FakePipeline.query success path is not configured")

    def index_documents(self, request):
        if self._error:
            raise self._error
        raise AssertionError("FakePipeline.index_documents success path is not configured")


@pytest.fixture
def mocked_api(tmp_path, monkeypatch):
    """TestClient with an isolated tmp ledger + a fake pipeline factory."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    monkeypatch.setattr(Config, "CHROMA_DB_PATH", str(chroma_dir))
    monkeypatch.setattr(Config, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "")  # auth off unless a test sets it

    test_ledger = RunLedger(str(tmp_path / "ledger.db"))
    app.dependency_overrides[get_ledger] = lambda: test_ledger
    server._pipelines.clear()
    server._ledger_singleton = None  # drop any real ledger a prior test may have built
    monkeypatch.setattr(
        server,
        "get_pipeline",
        lambda workspace_id="default": FakePipeline(tmp_path / f"ws_{workspace_id}"),
    )

    yield TestClient(app)

    app.dependency_overrides.clear()
    server._pipelines.clear()
    server._ledger_singleton = None
