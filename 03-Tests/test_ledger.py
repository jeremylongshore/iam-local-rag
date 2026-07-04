"""
Unit tests for RunLedger.
Tests SQLite storage, run recording, and workspace stats.
"""
import os
import tempfile
from datetime import datetime

import pytest

from nexus.core.ledger import RunLedger
from nexus.core.models import Citation, DocumentSource, IndexResult, QueryResponse


class TestRunLedger:
    """Test suite for RunLedger"""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
            db_path = f.name

        yield db_path

        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)

    @pytest.fixture
    def ledger(self, temp_db):
        """Create RunLedger instance with temp database"""
        return RunLedger(db_path=temp_db)

    def test_initialization_creates_database(self, temp_db):
        """Test database file is created on initialization"""
        RunLedger(db_path=temp_db)
        assert os.path.exists(temp_db)

    def test_initialization_creates_tables(self, ledger, temp_db):
        """Test database tables are created"""
        import sqlite3
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()

            # Check index_runs table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='index_runs'
            """)
            assert cursor.fetchone() is not None

            # Check query_runs table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='query_runs'
            """)
            assert cursor.fetchone() is not None

    def test_record_index_run(self, ledger):
        """Test recording an index run"""
        result = IndexResult(
            workspace_id="test_workspace",
            files_processed=5,
            files_skipped=1,
            total_chunks=100,
            processing_time_ms=1234.5,
            document_sources=[
                DocumentSource(
                    file_path="/path/to/doc.pdf",
                    file_hash="abc123",
                    file_mtime=1234567890.0,
                    indexed_at=datetime.now()
                )
            ]
        )

        run_id = ledger.record_index_run(result, embed_provider="OllamaEmbeddingProvider")

        assert run_id.startswith("idx_test_workspace_")

        # Verify it was recorded
        run = ledger.get_run(run_id)
        assert run is not None
        assert run["workspace_id"] == "test_workspace"
        assert run["files_processed"] == 5
        assert run["total_chunks"] == 100
        assert run["embed_provider"] == "OllamaEmbeddingProvider"

    def test_record_query_run(self, ledger):
        """Test recording a query run"""
        response = QueryResponse(
            question="What is the capital of France?",
            answer="Paris is the capital of France.",
            citations=[
                Citation(
                    source="geography.pdf",
                    page=10,
                    excerpt="Paris is the capital...",
                    relevance_score=0.95,
                    content_hash="hash123"
                )
            ],
            workspace_id="test_workspace",
            model_used="llama3",
            provider="OllamaLLMProvider",
            latency_ms=567.8,
            run_id="query_123",
            timestamp=datetime.now()
        )

        excerpt_hashes = ["hash_abc", "hash_def"]

        run_id = ledger.record_query_run(response, excerpt_hashes)

        assert run_id == "query_123"

        # Verify it was recorded
        run = ledger.get_run(run_id)
        assert run is not None
        assert run["workspace_id"] == "test_workspace"
        assert run["question"] == "What is the capital of France?"
        assert "Paris" in run["answer"]
        assert run["model_used"] == "llama3"
        assert run["citation_count"] == 1

    def test_list_runs_all(self, ledger):
        """Test listing all runs"""
        # Record an index run
        index_result = IndexResult(
            workspace_id="workspace1",
            files_processed=3,
            files_skipped=0,
            total_chunks=50,
            processing_time_ms=500.0,
            document_sources=[]
        )
        ledger.record_index_run(index_result, "OllamaEmbeddingProvider")

        # Record a query run
        query_response = QueryResponse(
            question="Test question",
            answer="Test answer",
            citations=[],
            workspace_id="workspace1",
            model_used="llama3",
            provider="OllamaLLMProvider",
            latency_ms=123.4,
            run_id="query_456",
            timestamp=datetime.now()
        )
        ledger.record_query_run(query_response, [])

        # List all runs
        runs = ledger.list_runs(run_type="all", limit=100)

        assert "index_runs" in runs
        assert "query_runs" in runs
        assert len(runs["index_runs"]) >= 1
        assert len(runs["query_runs"]) >= 1

    def test_list_runs_workspace_filter(self, ledger):
        """Test filtering runs by workspace"""
        # Record runs for different workspaces
        for workspace in ["ws1", "ws2"]:
            index_result = IndexResult(
                workspace_id=workspace,
                files_processed=1,
                files_skipped=0,
                total_chunks=10,
                processing_time_ms=100.0,
                document_sources=[]
            )
            ledger.record_index_run(index_result, "OllamaEmbeddingProvider")

        # List runs for ws1 only
        runs = ledger.list_runs(workspace_id="ws1", run_type="index")

        assert len(runs["index_runs"]) >= 1
        for run in runs["index_runs"]:
            assert run["workspace_id"] == "ws1"

    def test_list_runs_type_filter(self, ledger):
        """Test filtering runs by type"""
        # Record both types
        index_result = IndexResult(
            workspace_id="ws",
            files_processed=1,
            files_skipped=0,
            total_chunks=10,
            processing_time_ms=100.0,
            document_sources=[]
        )
        ledger.record_index_run(index_result, "OllamaEmbeddingProvider")

        query_response = QueryResponse(
            question="Q",
            answer="A",
            citations=[],
            workspace_id="ws",
            model_used="llama3",
            provider="OllamaLLMProvider",
            latency_ms=100.0,
            run_id="q1",
            timestamp=datetime.now()
        )
        ledger.record_query_run(query_response, [])

        # List only query runs
        runs = ledger.list_runs(run_type="query")

        assert len(runs["query_runs"]) >= 1
        assert len(runs["index_runs"]) == 0  # Should be empty

    def test_list_runs_limit(self, ledger):
        """Test limit parameter works"""
        # Record multiple runs
        for i in range(10):
            query_response = QueryResponse(
                question=f"Question {i}",
                answer=f"Answer {i}",
                citations=[],
                workspace_id="ws",
                model_used="llama3",
                provider="OllamaLLMProvider",
                latency_ms=100.0,
                run_id=f"q{i}",
                timestamp=datetime.now()
            )
            ledger.record_query_run(query_response, [])

        # List with limit
        runs = ledger.list_runs(run_type="query", limit=5)

        assert len(runs["query_runs"]) <= 5

    def test_get_run_not_found(self, ledger):
        """Test get_run returns None for non-existent run"""
        run = ledger.get_run("nonexistent_id")
        assert run is None

    def test_get_run_includes_type(self, ledger):
        """Test get_run includes run_type field"""
        # Record index run
        index_result = IndexResult(
            workspace_id="ws",
            files_processed=1,
            files_skipped=0,
            total_chunks=10,
            processing_time_ms=100.0,
            document_sources=[]
        )
        run_id = ledger.record_index_run(index_result, "OllamaEmbeddingProvider")

        run = ledger.get_run(run_id)
        assert run["run_type"] == "index"

    def test_get_workspace_stats(self, ledger):
        """Test workspace statistics aggregation"""
        workspace_id = "stats_test"

        # Record some index runs
        for i in range(3):
            index_result = IndexResult(
                workspace_id=workspace_id,
                files_processed=5,
                files_skipped=0,
                total_chunks=100,
                processing_time_ms=500.0,
                document_sources=[]
            )
            ledger.record_index_run(index_result, "OllamaEmbeddingProvider")

        # Record some query runs
        for i in range(5):
            query_response = QueryResponse(
                question=f"Q{i}",
                answer=f"A{i}",
                citations=[Citation(
                    source="doc.pdf",
                    page=1,
                    excerpt="excerpt",
                    relevance_score=0.9,
                    content_hash="hash"
                )],
                workspace_id=workspace_id,
                model_used="llama3",
                provider="OllamaLLMProvider",
                latency_ms=200.0,
                run_id=f"q{i}",
                timestamp=datetime.now()
            )
            ledger.record_query_run(query_response, [])

        stats = ledger.get_workspace_stats(workspace_id)

        assert stats["workspace_id"] == workspace_id
        assert stats["index_runs"]["total"] == 3
        assert stats["index_runs"]["total_files"] == 15  # 3 runs * 5 files
        assert stats["query_runs"]["total"] == 5
        assert stats["query_runs"]["avg_citations"] == 1.0

    def test_cleanup_old_runs(self, ledger):
        """Test cleanup of old runs"""
        # Record a query run
        query_response = QueryResponse(
            question="Old question",
            answer="Old answer",
            citations=[],
            workspace_id="ws",
            model_used="llama3",
            provider="OllamaLLMProvider",
            latency_ms=100.0,
            run_id="old_query",
            timestamp=datetime.now()
        )
        ledger.record_query_run(query_response, [])

        # Cleanup is exception-gated on the tamper-evident ledger; opt in explicitly.
        deleted = ledger.cleanup_old_runs(days=0, allow_delete=True)

        # Should have deleted at least 1 run
        assert deleted >= 1

        # Verify run is gone
        run = ledger.get_run("old_query")
        assert run is None
