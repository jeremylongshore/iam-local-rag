"""
Blocking-gate API wiring tests (000-docs/009 #6): endpoint routing, serialization,
validation, and error-handling with a mocked pipeline + isolated tmp ledger — no
Ollama. Previously the ONLY end-to-end API coverage lived in `test_api.py` under
`@pytest.mark.integration`, whose CI job is `continue-on-error`, so a wiring
regression (routing, a 500 handler, the ledger dependency) could not fail a build.

The happy-path index/query semantics (real embeddings + generation) stay in the
integration suite; here we prove the plumbing.
"""
from conftest import FakePipeline

import nexus.api.server as server
from nexus.core.config import Config


def test_root_lists_endpoints(mocked_api):
    r = mocked_api.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "NEXUS RAG API"
    assert "endpoints" in body


def test_health_reports_vector_store_readiness(mocked_api):
    r = mocked_api.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["vector_store_ready"] is False  # FakePipeline.retriever.exists() -> False


def test_create_workspace_empty_id_rejected(mocked_api):
    assert mocked_api.post("/workspaces?workspace_id=").status_code == 400


def test_create_workspace_traversal_rejected(mocked_api):
    assert mocked_api.post("/workspaces?workspace_id=../evil").status_code == 400


def test_create_workspace_success(mocked_api):
    r = mocked_api.post("/workspaces?workspace_id=good_ws")
    assert r.status_code == 200
    body = r.json()
    assert body["workspace_id"] == "good_ws"
    assert body["status"] == "created"


def test_list_runs_returns_shape_on_empty_ledger(mocked_api):
    r = mocked_api.get("/runs")
    assert r.status_code == 200
    body = r.json()
    assert "index_runs" in body and "query_runs" in body


def test_get_run_404_for_unknown_id(mocked_api):
    assert mocked_api.get("/runs/does-not-exist").status_code == 404


def test_audit_verify_ok_on_empty_chain(mocked_api):
    r = mocked_api.get("/audit/verify")
    assert r.status_code == 200
    assert r.json()["ok"] is True  # an empty hash-chain verifies


def test_query_pipeline_error_returns_500(mocked_api, monkeypatch, tmp_path):
    monkeypatch.setattr(
        server,
        "get_pipeline",
        lambda workspace_id="default": FakePipeline(tmp_path / "x", error=RuntimeError("boom")),
    )
    r = mocked_api.post("/query", json={"question": "q", "workspace_id": "w"})
    assert r.status_code == 500


def test_index_pipeline_error_returns_500(mocked_api, monkeypatch, tmp_path):
    monkeypatch.setattr(
        server,
        "get_pipeline",
        lambda workspace_id="default": FakePipeline(tmp_path / "x", error=RuntimeError("boom")),
    )
    r = mocked_api.post("/index", json={"paths": ["/nope"], "workspace_id": "w"})
    assert r.status_code == 500


def test_cors_allowlist_not_wildcard_by_default():
    # Default config must NOT be an open "*" CORS origin with this mutating API.
    assert "*" not in Config.NEXUS_CORS_ORIGINS or Config.NEXUS_CORS_ORIGINS == []
