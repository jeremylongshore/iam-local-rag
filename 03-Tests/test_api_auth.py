"""
API auth + CORS unit tests (P4). Auth is checked before the endpoint body, so a
401 needs no Ollama/pipeline — these stay in the unit gate.
"""
from fastapi.testclient import TestClient

from nexus.api.server import app
from nexus.core.config import Config


def test_protected_endpoint_401_without_key(monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    client = TestClient(app)
    r = client.post("/query", json={"question": "q", "workspace_id": "w"})
    assert r.status_code == 401


def test_protected_endpoint_wrong_key_401(monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    client = TestClient(app)
    r = client.get("/runs", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_bearer_key_accepted(monkeypatch, tmp_path):
    # A valid key passes auth; /runs then succeeds (reads the ledger, no Ollama).
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    client = TestClient(app)
    r = client.get("/runs", headers={"Authorization": "Bearer secret123"})
    assert r.status_code != 401


def test_health_open_without_key(monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200  # health is intentionally unauthenticated


def test_auth_noop_when_key_unset(monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", None)
    client = TestClient(app)
    r = client.get("/runs")  # no key needed in local-dev default
    assert r.status_code != 401


def test_create_workspace_rejects_path_traversal(monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", None)  # auth off → reach the handler
    client = TestClient(app)
    r = client.post("/workspaces", params={"workspace_id": "../../etc"})
    assert r.status_code == 400  # rejected before any makedirs
