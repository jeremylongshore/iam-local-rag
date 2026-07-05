"""
API tests for the NEXUS FastAPI server (INTEGRATION — needs Ollama for the real
index/query paths). Endpoint routing / serialization / error-handling that does
NOT need a live model lives in the blocking `test_api_mocked.py`.

The ledger is injected via `app.dependency_overrides[get_ledger]` (not a module
global), and all temp files use pytest's `tmp_path` — no `tempfile.mkdtemp()`
leaks (000-docs/009 #9, #25).
"""
import pytest
from fastapi.testclient import TestClient

import nexus.api.server as server
from nexus.api.server import app, get_ledger
from nexus.core.config import Config
from nexus.core.ledger import RunLedger

# Exercises the pipeline end-to-end (Ollama for LLM + embeddings) — unit gate skips it.
pytestmark = pytest.mark.integration


class TestNexusAPI:
    """Test suite for the NEXUS REST API."""

    @pytest.fixture
    def client(self, tmp_path):
        """Test client with temp config + an isolated, dependency-injected ledger."""
        chroma_dir = tmp_path / "chroma"
        chroma_dir.mkdir()
        ledger_path = str(tmp_path / "ledger.db")

        original_chroma = Config.CHROMA_DB_PATH
        original_ledger = Config.LEDGER_DB_PATH
        Config.CHROMA_DB_PATH = str(chroma_dir)
        Config.LEDGER_DB_PATH = ledger_path

        server._pipelines.clear()
        test_ledger = RunLedger(ledger_path)
        app.dependency_overrides[get_ledger] = lambda: test_ledger

        yield TestClient(app)

        server._pipelines.clear()
        app.dependency_overrides.clear()
        Config.CHROMA_DB_PATH = original_chroma
        Config.LEDGER_DB_PATH = original_ledger

    @staticmethod
    def _doc(tmp_path, content="Sample content for testing indexing", name="sample.txt"):
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir(exist_ok=True)
        doc = docs_dir / name
        doc.write_text(content)
        return str(doc)

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "NEXUS RAG API"
        assert data["version"] == "1.1.0"
        assert "endpoints" in data

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "mode" in data
        assert "llm_provider" in data
        assert "embed_provider" in data
        assert "uptime_seconds" in data

    def test_create_workspace(self, client):
        response = client.post("/workspaces?workspace_id=test_ws")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "test_ws"
        assert data["status"] == "created"
        assert "chroma_path" in data

    def test_create_workspace_missing_id(self, client):
        response = client.post("/workspaces?workspace_id=")
        assert response.status_code == 400

    def test_list_workspaces_empty(self, client):
        response = client.get("/workspaces")
        assert response.status_code == 200
        data = response.json()
        assert "workspaces" in data
        assert data["total"] == 0

    def test_list_workspaces_with_data(self, client):
        client.post("/workspaces?workspace_id=ws1")
        response = client.get("/workspaces")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert "ws1" in [ws["workspace_id"] for ws in data["workspaces"]]

    def test_index_documents(self, client, tmp_path):
        doc_path = self._doc(tmp_path)
        response = client.post(
            "/index",
            json={"paths": [doc_path], "workspace_id": "test_index", "force_reindex": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == "test_index"
        assert data["files_processed"] >= 1
        assert data["total_chunks"] > 0

    def test_query_without_documents(self, client):
        response = client.post(
            "/query", json={"question": "What is this?", "workspace_id": "empty_workspace"}
        )
        assert response.status_code == 500  # no documents indexed

    def test_query_with_documents(self, client, tmp_path):
        doc_path = self._doc(
            tmp_path,
            content=(
                "Artificial intelligence is the simulation of human intelligence. "
                "Machine learning is a subset of AI."
            ),
        )
        client.post("/index", json={"paths": [doc_path], "workspace_id": "test_query"})
        response = client.post(
            "/query", json={"question": "What is machine learning?", "workspace_id": "test_query"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["question"] == "What is machine learning?"
        assert "answer" in data
        assert "citations" in data
        assert data["workspace_id"] == "test_query"
        assert "run_id" in data

    def test_list_runs_empty(self, client):
        response = client.get("/runs")
        assert response.status_code == 200
        data = response.json()
        assert "index_runs" in data
        assert "query_runs" in data

    def test_list_runs_with_data(self, client, tmp_path):
        doc_path = self._doc(tmp_path, content="Content for run tracking")
        client.post("/index", json={"paths": [doc_path], "workspace_id": "test_runs"})
        client.post("/query", json={"question": "Test", "workspace_id": "test_runs"})
        response = client.get("/runs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["index_runs"]) >= 1
        assert len(data["query_runs"]) >= 1

    def test_list_runs_workspace_filter(self, client, tmp_path):
        doc_path = self._doc(tmp_path, content="Content")
        client.post("/index", json={"paths": [doc_path], "workspace_id": "ws1"})
        client.post("/index", json={"paths": [doc_path], "workspace_id": "ws2"})
        response = client.get("/runs?workspace_id=ws1")
        assert response.status_code == 200
        for run in response.json()["index_runs"]:
            assert run["workspace_id"] == "ws1"

    def test_list_runs_type_filter(self, client, tmp_path):
        doc_path = self._doc(tmp_path, content="Content")
        client.post("/index", json={"paths": [doc_path], "workspace_id": "test"})
        response = client.get("/runs?run_type=index")
        assert response.status_code == 200
        data = response.json()
        assert len(data["index_runs"]) >= 1
        assert len(data["query_runs"]) == 0

    def test_list_runs_limit(self, client, tmp_path):
        doc_path = self._doc(tmp_path, content="Content")
        client.post("/index", json={"paths": [doc_path], "workspace_id": "test"})
        for i in range(5):
            client.post("/query", json={"question": f"Question {i}", "workspace_id": "test"})
        response = client.get("/runs?run_type=query&limit=3")
        assert response.status_code == 200
        assert len(response.json()["query_runs"]) <= 3

    def test_get_run_not_found(self, client):
        response = client.get("/runs/nonexistent_run_id")
        assert response.status_code == 404

    def test_get_run_success(self, client, tmp_path):
        doc_path = self._doc(tmp_path, content="Content")
        client.post("/index", json={"paths": [doc_path], "workspace_id": "test"})
        query_response = client.post("/query", json={"question": "Test", "workspace_id": "test"})
        run_id = query_response.json()["run_id"]
        response = client.get(f"/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["workspace_id"] == "test"
        assert "run_type" in data
