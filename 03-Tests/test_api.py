"""
API tests for NEXUS FastAPI server.
Tests REST endpoints using FastAPI TestClient.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from nexus.api.server import app
from nexus.core.config import Config

# Exercises the pipeline end-to-end (Ollama for LLM + embeddings) — unit gate skips it.
pytestmark = pytest.mark.integration


class TestNexusAPI:
    """Test suite for NEXUS REST API"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as chroma_dir, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".db") as ledger_file:

            ledger_path = ledger_file.name

            yield {
                "chroma_dir": chroma_dir,
                "ledger_path": ledger_path
            }

            # Cleanup
            if os.path.exists(ledger_path):
                os.remove(ledger_path)

    @pytest.fixture
    def client(self, temp_dirs):
        """Create test client with temp config + isolated server state."""
        import nexus.api.server as server
        from nexus.core.ledger import RunLedger

        # Patch config
        original_chroma = Config.CHROMA_DB_PATH
        original_ledger = Config.LEDGER_DB_PATH

        Config.CHROMA_DB_PATH = temp_dirs["chroma_dir"]
        Config.LEDGER_DB_PATH = temp_dirs["ledger_path"]

        # Reset the server's module-level state so each test is isolated and the
        # ledger/pipelines use the patched temp paths (not the import-time paths).
        server._pipelines.clear()
        server._ledger = RunLedger(temp_dirs["ledger_path"])

        client = TestClient(app)

        yield client

        server._pipelines.clear()

        # Restore config
        Config.CHROMA_DB_PATH = original_chroma
        Config.LEDGER_DB_PATH = original_ledger

    def test_root_endpoint(self, client):
        """Test root endpoint returns service info"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["service"] == "NEXUS RAG API"
        assert data["version"] == "1.1.0"
        assert "endpoints" in data

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert "mode" in data
        assert "llm_provider" in data
        assert "embed_provider" in data
        assert "uptime_seconds" in data

    def test_create_workspace(self, client):
        """Test creating a new workspace"""
        response = client.post("/workspaces?workspace_id=test_ws")

        assert response.status_code == 200
        data = response.json()

        assert data["workspace_id"] == "test_ws"
        assert data["status"] == "created"
        assert "chroma_path" in data

    def test_create_workspace_missing_id(self, client):
        """Test creating workspace without ID fails"""
        response = client.post("/workspaces?workspace_id=")

        assert response.status_code == 400

    def test_list_workspaces_empty(self, client):
        """Test listing workspaces when none exist"""
        response = client.get("/workspaces")

        assert response.status_code == 200
        data = response.json()

        assert "workspaces" in data
        assert "total" in data
        assert data["total"] == 0

    def test_list_workspaces_with_data(self, client, temp_dirs):
        """Test listing workspaces after creating some"""
        # Create a workspace
        client.post("/workspaces?workspace_id=ws1")

        # List workspaces
        response = client.get("/workspaces")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] >= 1
        workspace_ids = [ws["workspace_id"] for ws in data["workspaces"]]
        assert "ws1" in workspace_ids

    def test_index_documents(self, client, temp_dirs):
        """Test indexing documents via API"""
        # Create sample document
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Sample content for testing indexing")

        # Index request
        request = {
            "paths": [doc_path],
            "workspace_id": "test_index",
            "force_reindex": False
        }

        response = client.post("/index", json=request)

        assert response.status_code == 200
        data = response.json()

        assert data["workspace_id"] == "test_index"
        assert data["files_processed"] >= 1
        assert data["total_chunks"] > 0

    def test_query_without_documents(self, client):
        """Test querying empty workspace fails"""
        request = {
            "question": "What is this?",
            "workspace_id": "empty_workspace"
        }

        response = client.post("/query", json=request)

        # Should fail because no documents indexed
        assert response.status_code == 500

    def test_query_with_documents(self, client, temp_dirs):
        """Test querying after indexing documents"""
        # Create sample document
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("""
            Artificial intelligence is the simulation of human intelligence.
            Machine learning is a subset of AI.
            """)

        # Index
        index_request = {
            "paths": [doc_path],
            "workspace_id": "test_query"
        }
        client.post("/index", json=index_request)

        # Query
        query_request = {
            "question": "What is machine learning?",
            "workspace_id": "test_query"
        }

        response = client.post("/query", json=query_request)

        assert response.status_code == 200
        data = response.json()

        assert data["question"] == "What is machine learning?"
        assert "answer" in data
        assert "citations" in data
        assert data["workspace_id"] == "test_query"
        assert "run_id" in data

    def test_list_runs_empty(self, client):
        """Test listing runs when none exist"""
        response = client.get("/runs")

        assert response.status_code == 200
        data = response.json()

        assert "index_runs" in data
        assert "query_runs" in data

    def test_list_runs_with_data(self, client, temp_dirs):
        """Test listing runs after operations"""
        # Create sample document
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Content for run tracking")

        # Index
        index_request = {
            "paths": [doc_path],
            "workspace_id": "test_runs"
        }
        client.post("/index", json=index_request)

        # Query
        query_request = {
            "question": "Test",
            "workspace_id": "test_runs"
        }
        client.post("/query", json=query_request)

        # List all runs
        response = client.get("/runs")

        assert response.status_code == 200
        data = response.json()

        assert len(data["index_runs"]) >= 1
        assert len(data["query_runs"]) >= 1

    def test_list_runs_workspace_filter(self, client, temp_dirs):
        """Test filtering runs by workspace"""
        # Create docs for two workspaces
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Content")

        # Index in ws1
        client.post("/index", json={
            "paths": [doc_path],
            "workspace_id": "ws1"
        })

        # Index in ws2
        client.post("/index", json={
            "paths": [doc_path],
            "workspace_id": "ws2"
        })

        # List runs for ws1 only
        response = client.get("/runs?workspace_id=ws1")

        assert response.status_code == 200
        data = response.json()

        # All runs should be from ws1
        for run in data["index_runs"]:
            assert run["workspace_id"] == "ws1"

    def test_list_runs_type_filter(self, client, temp_dirs):
        """Test filtering runs by type"""
        # Create document
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Content")

        # Index
        client.post("/index", json={
            "paths": [doc_path],
            "workspace_id": "test"
        })

        # List only index runs
        response = client.get("/runs?run_type=index")

        assert response.status_code == 200
        data = response.json()

        assert len(data["index_runs"]) >= 1
        assert len(data["query_runs"]) == 0

    def test_list_runs_limit(self, client, temp_dirs):
        """Test limit parameter"""
        # Create multiple runs
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Content")

        # Create 5 query runs
        client.post("/index", json={
            "paths": [doc_path],
            "workspace_id": "test"
        })

        for i in range(5):
            client.post("/query", json={
                "question": f"Question {i}",
                "workspace_id": "test"
            })

        # List with limit
        response = client.get("/runs?run_type=query&limit=3")

        assert response.status_code == 200
        data = response.json()

        assert len(data["query_runs"]) <= 3

    def test_get_run_not_found(self, client):
        """Test getting non-existent run returns 404"""
        response = client.get("/runs/nonexistent_run_id")

        assert response.status_code == 404

    def test_get_run_success(self, client, temp_dirs):
        """Test getting specific run details"""
        # Create document and index
        docs_dir = tempfile.mkdtemp()
        doc_path = os.path.join(docs_dir, "sample.txt")
        with open(doc_path, "w") as f:
            f.write("Content")

        # Index
        client.post("/index", json={
            "paths": [doc_path],
            "workspace_id": "test"
        })

        # Query to create a run
        query_response = client.post("/query", json={
            "question": "Test",
            "workspace_id": "test"
        })

        run_id = query_response.json()["run_id"]

        # Get run details
        response = client.get(f"/runs/{run_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["run_id"] == run_id
        assert data["workspace_id"] == "test"
        assert "run_type" in data
