"""
Run ledger for NEXUS - audit trail and run history.
SQLite-based storage for tracking document indexing and query runs.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config
from .models import IndexResult, QueryResponse


class RunLedger:
    """
    SQLite-based run ledger for tracking NEXUS operations.
    Stores audit trail of index runs and query runs per workspace.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize run ledger.

        Args:
            db_path: Path to SQLite database (defaults to Config.LEDGER_DB_PATH)
        """
        self.db_path = db_path or Config.LEDGER_DB_PATH

        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Index runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS index_runs (
                    run_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    files_processed INTEGER NOT NULL,
                    files_skipped INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    processing_time_ms REAL NOT NULL,
                    document_sources TEXT NOT NULL,
                    embed_provider TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Query runs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS query_runs (
                    run_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    max_results INTEGER NOT NULL,
                    model_used TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    citation_count INTEGER NOT NULL,
                    excerpt_hashes TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Workspace index
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_index_workspace
                ON index_runs(workspace_id, timestamp DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_query_workspace
                ON query_runs(workspace_id, timestamp DESC)
            """)

            conn.commit()

    def record_index_run(
        self,
        result: IndexResult,
        embed_provider: str
    ) -> str:
        """
        Record an index run to the ledger.

        Args:
            result: IndexResult from RAG pipeline
            embed_provider: Name of embedding provider used

        Returns:
            run_id for this index operation
        """
        # Generate run_id if not present
        run_id = f"idx_{result.workspace_id}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

        # Serialize document sources
        sources_json = json.dumps([
            {
                "file_path": src.file_path,
                "file_hash": src.file_hash,
                "file_mtime": src.file_mtime,
                "indexed_at": src.indexed_at.isoformat() if src.indexed_at else None
            }
            for src in result.document_sources
        ])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO index_runs (
                    run_id, workspace_id, timestamp,
                    files_processed, files_skipped, total_chunks,
                    processing_time_ms, document_sources, embed_provider
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                result.workspace_id,
                datetime.now().isoformat(),
                result.files_processed,
                result.files_skipped,
                result.total_chunks,
                result.processing_time_ms,
                sources_json,
                embed_provider
            ))
            conn.commit()

        return run_id

    def record_query_run(
        self,
        response: QueryResponse,
        excerpt_hashes: Optional[List[str]] = None
    ) -> str:
        """
        Record a query run to the ledger.

        Args:
            response: QueryResponse from RAG pipeline
            excerpt_hashes: Optional list of excerpt hashes (for hybrid safety audit)

        Returns:
            run_id from the response
        """
        # Serialize excerpt hashes
        hashes_json = json.dumps(excerpt_hashes or [])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO query_runs (
                    run_id, workspace_id, timestamp,
                    question, answer, max_results,
                    model_used, provider, latency_ms,
                    citation_count, excerpt_hashes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                response.run_id,
                response.workspace_id,
                response.timestamp.isoformat(),
                response.question[:500],  # Truncate long questions
                response.answer[:2000],  # Truncate long answers
                len(response.citations),  # max_results is citation count
                response.model_used,
                response.provider,
                response.latency_ms,
                len(response.citations),
                hashes_json
            ))
            conn.commit()

        return response.run_id

    def list_runs(
        self,
        workspace_id: Optional[str] = None,
        run_type: str = "all",
        limit: int = 100
    ) -> Dict[str, List[Dict]]:
        """
        List recent runs from the ledger.

        Args:
            workspace_id: Filter by workspace (None = all workspaces)
            run_type: "index", "query", or "all"
            limit: Max runs to return per type

        Returns:
            Dict with "index_runs" and "query_runs" lists
        """
        results = {
            "index_runs": [],
            "query_runs": []
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Fetch index runs
            if run_type in ["index", "all"]:
                query = """
                    SELECT * FROM index_runs
                    WHERE 1=1
                """
                params = []

                if workspace_id:
                    query += " AND workspace_id = ?"
                    params.append(workspace_id)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(query, params)
                results["index_runs"] = [dict(row) for row in cursor.fetchall()]

            # Fetch query runs
            if run_type in ["query", "all"]:
                query = """
                    SELECT * FROM query_runs
                    WHERE 1=1
                """
                params = []

                if workspace_id:
                    query += " AND workspace_id = ?"
                    params.append(workspace_id)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(query, params)
                results["query_runs"] = [dict(row) for row in cursor.fetchall()]

        return results

    def get_run(self, run_id: str) -> Optional[Dict]:
        """
        Get details for a specific run.

        Args:
            run_id: Run ID to fetch

        Returns:
            Run details dict or None if not found
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Try index runs
            cursor = conn.execute(
                "SELECT * FROM index_runs WHERE run_id = ?",
                (run_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result["run_type"] = "index"
                return result

            # Try query runs
            cursor = conn.execute(
                "SELECT * FROM query_runs WHERE run_id = ?",
                (run_id,)
            )
            row = cursor.fetchone()
            if row:
                result = dict(row)
                result["run_type"] = "query"
                return result

        return None

    def get_workspace_stats(self, workspace_id: str) -> Dict:
        """
        Get statistics for a workspace.

        Args:
            workspace_id: Workspace to analyze

        Returns:
            Dict with stats (total_index_runs, total_query_runs, etc.)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Index stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_runs,
                    SUM(files_processed) as total_files,
                    SUM(total_chunks) as total_chunks,
                    AVG(processing_time_ms) as avg_processing_time
                FROM index_runs
                WHERE workspace_id = ?
            """, (workspace_id,))
            index_stats = cursor.fetchone()

            # Query stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_runs,
                    AVG(latency_ms) as avg_latency,
                    AVG(citation_count) as avg_citations
                FROM query_runs
                WHERE workspace_id = ?
            """, (workspace_id,))
            query_stats = cursor.fetchone()

            return {
                "workspace_id": workspace_id,
                "index_runs": {
                    "total": index_stats[0],
                    "total_files": index_stats[1] or 0,
                    "total_chunks": index_stats[2] or 0,
                    "avg_processing_time_ms": index_stats[3] or 0.0
                },
                "query_runs": {
                    "total": query_stats[0],
                    "avg_latency_ms": query_stats[1] or 0.0,
                    "avg_citations": query_stats[2] or 0.0
                }
            }

    def cleanup_old_runs(self, days: int = 90) -> int:
        """
        Delete runs older than specified days.

        Args:
            days: Delete runs older than this many days

        Returns:
            Number of runs deleted
        """
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM index_runs WHERE timestamp < ?",
                (cutoff_iso,)
            )
            index_deleted = cursor.rowcount

            cursor.execute(
                "DELETE FROM query_runs WHERE timestamp < ?",
                (cutoff_iso,)
            )
            query_deleted = cursor.rowcount

            conn.commit()

        return index_deleted + query_deleted
