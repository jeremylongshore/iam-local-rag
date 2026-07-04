"""
Unit tests for the tamper-evident audit hash-chain (P4 trust moat).
"""
import sqlite3
from datetime import datetime

import pytest

from nexus.core.ledger import RunLedger
from nexus.core.models import IndexResult, QueryResponse


def _index_result(ws="w"):
    return IndexResult(
        workspace_id=ws,
        files_processed=1,
        files_skipped=0,
        total_chunks=3,
        processing_time_ms=1.0,
        document_sources=[],
    )


def _query_response(ws="w", run_id="r1"):
    return QueryResponse(
        question="q",
        answer="a",
        citations=[],
        workspace_id=ws,
        model_used="m",
        provider="p",
        latency_ms=1.0,
        run_id=run_id,
        timestamp=datetime.now(),
    )


def test_chain_verifies_after_appends(tmp_path):
    led = RunLedger(str(tmp_path / "l.db"))
    led.record_index_run(_index_result(), "ollama")
    led.record_query_run(_query_response(run_id="r1"))
    led.record_query_run(_query_response(run_id="r2"))
    v = led.verify_chain()
    assert v["ok"] is True
    assert v["total"] == 3
    assert v["breaks"] == []


def test_chain_detects_content_tampering(tmp_path):
    led = RunLedger(str(tmp_path / "l.db"))
    led.record_index_run(_index_result(), "ollama")
    led.record_query_run(_query_response(run_id="r1"))

    # Simulate an attacker editing the DB in place.
    with sqlite3.connect(led.db_path) as c:
        c.execute("UPDATE audit_chain SET payload_hash='TAMPERED' WHERE seq=1")
        c.commit()

    v = led.verify_chain()
    assert v["ok"] is False
    assert any("row_hash mismatch" in b["reason"] for b in v["breaks"])


def test_chain_detects_reorder_or_link_break(tmp_path):
    led = RunLedger(str(tmp_path / "l.db"))
    led.record_index_run(_index_result(), "ollama")
    led.record_query_run(_query_response(run_id="r1"))

    # Break the link: null out a prev_hash mid-chain.
    with sqlite3.connect(led.db_path) as c:
        c.execute("UPDATE audit_chain SET prev_hash=NULL WHERE seq=2")
        c.commit()

    v = led.verify_chain()
    assert v["ok"] is False


def test_cleanup_is_delete_gated(tmp_path):
    led = RunLedger(str(tmp_path / "l.db"))
    led.record_index_run(_index_result(), "ollama")
    with pytest.raises(PermissionError):
        led.cleanup_old_runs(days=0)  # append-only by default
    # Explicit opt-in is allowed.
    led.cleanup_old_runs(days=0, allow_delete=True)
