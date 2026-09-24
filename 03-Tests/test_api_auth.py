"""
API auth + CORS unit tests (P4). Auth is checked before the endpoint body, so a
401 needs no Ollama/pipeline — these stay in the unit gate. They use the shared
`mocked_api` fixture (conftest.py) so the authenticated `/runs`/`/health` paths hit
an isolated tmp ledger + fake pipeline, never a real ./nexus_ledger.db (009 #9).
"""
from nexus.core.config import Config


def test_protected_endpoint_401_without_key(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.post("/query", json={"question": "q", "workspace_id": "w"})
    assert r.status_code == 401


def test_protected_endpoint_wrong_key_401(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.get("/runs", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_bearer_key_accepted(mocked_api, monkeypatch):
    # A valid key passes auth; /runs then succeeds (reads the isolated ledger).
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.get("/runs", headers={"Authorization": "Bearer secret123"})
    assert r.status_code == 200
    assert "index_runs" in r.json()  # reached the handler, not a 401


def test_bearer_key_tolerates_extra_whitespace(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.get("/runs", headers={"Authorization": "Bearer   secret123"})
    assert r.status_code == 200  # extra spaces must not break auth


def test_x_api_key_header_accepted(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.get("/runs", headers={"X-API-Key": "secret123"})
    assert r.status_code == 200


def test_health_open_without_key(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", "secret123")
    r = mocked_api.get("/health")
    assert r.status_code == 200  # health is intentionally unauthenticated


def test_auth_noop_when_key_unset(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", None)
    r = mocked_api.get("/runs")  # no key needed in local-dev default
    assert r.status_code == 200


def test_create_workspace_rejects_path_traversal(mocked_api, monkeypatch):
    monkeypatch.setattr(Config, "NEXUS_API_KEY", None)  # auth off → reach the handler
    r = mocked_api.post("/workspaces", params={"workspace_id": "../../etc"})
    assert r.status_code == 400  # rejected before any makedirs
