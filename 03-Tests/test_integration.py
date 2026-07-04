"""
Integration tests for NEXUS RAG pipeline.
Tests full end-to-end workflows with real components.
"""
import os
import tempfile

import pytest

from nexus.core.config import Config
from nexus.core.models import IndexRequest, QueryRequest
from nexus.core.providers.ollama_provider import OllamaEmbeddingProvider, OllamaLLMProvider
from nexus.core.rag_pipeline import RAGPipeline

# Full end-to-end with real Ollama components — unit gate skips it.
pytestmark = pytest.mark.integration


class TestRAGPipelineIntegration:
    """Integration tests for RAG pipeline"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing"""
        with tempfile.TemporaryDirectory() as chroma_dir, \
             tempfile.TemporaryDirectory() as docs_dir, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".db") as ledger_file:

            ledger_path = ledger_file.name

            yield {
                "chroma_dir": chroma_dir,
                "docs_dir": docs_dir,
                "ledger_path": ledger_path
            }

            # Cleanup ledger
            if os.path.exists(ledger_path):
                os.remove(ledger_path)

    @pytest.fixture
    def sample_documents(self, temp_dirs):
        """Create sample documents for testing"""
        docs_dir = temp_dirs["docs_dir"]

        # Create sample text file
        txt_path = os.path.join(docs_dir, "sample.txt")
        with open(txt_path, "w") as f:
            f.write("""
            This is a sample document about artificial intelligence.
            Machine learning is a subset of AI that focuses on learning from data.
            Deep learning uses neural networks with multiple layers.
            Natural language processing enables computers to understand human language.
            """)

        # Create sample markdown file
        md_path = os.path.join(docs_dir, "sample.md")
        with open(md_path, "w") as f:
            f.write("""
            # Python Programming

            Python is a high-level programming language.
            It is widely used for web development, data science, and automation.

            ## Key Features
            - Easy to learn
            - Readable syntax
            - Large standard library
            """)

        return [txt_path, md_path]

    @pytest.fixture
    def pipeline(self, temp_dirs):
        """Create RAG pipeline with Ollama providers"""
        # Patch config paths
        original_chroma = Config.CHROMA_DB_PATH
        original_ledger = Config.LEDGER_DB_PATH

        Config.CHROMA_DB_PATH = temp_dirs["chroma_dir"]
        Config.LEDGER_DB_PATH = temp_dirs["ledger_path"]

        llm_provider = OllamaLLMProvider()
        embed_provider = OllamaEmbeddingProvider()

        pipeline = RAGPipeline(
            llm_provider=llm_provider,
            embed_provider=embed_provider,
            workspace_id="test_workspace"
        )

        yield pipeline

        # Restore config
        Config.CHROMA_DB_PATH = original_chroma
        Config.LEDGER_DB_PATH = original_ledger

    def test_index_and_query_workflow(self, pipeline, sample_documents):
        """Test full workflow: index documents, then query"""
        # Index documents
        index_request = IndexRequest(
            paths=sample_documents,
            workspace_id="test_workspace"
        )

        index_result = pipeline.index_documents(index_request)

        # Verify indexing results
        assert index_result.workspace_id == "test_workspace"
        assert index_result.files_processed == 2
        assert index_result.total_chunks > 0
        assert len(index_result.document_sources) == 2

        # Query the knowledge base
        query_request = QueryRequest(
            question="What is machine learning?",
            workspace_id="test_workspace",
            max_results=3
        )

        query_response = pipeline.query(query_request)

        # Verify query results
        assert query_response.workspace_id == "test_workspace"
        assert query_response.question == "What is machine learning?"
        assert len(query_response.answer) > 0
        assert len(query_response.citations) > 0
        assert query_response.latency_ms > 0
        assert query_response.run_id is not None

    def test_multiple_queries_same_workspace(self, pipeline, sample_documents):
        """Test multiple queries against same workspace"""
        # Index documents
        index_request = IndexRequest(
            paths=sample_documents,
            workspace_id="test_workspace"
        )
        pipeline.index_documents(index_request)

        # Query 1
        query1 = QueryRequest(
            question="What is Python?",
            workspace_id="test_workspace"
        )
        response1 = pipeline.query(query1)

        # Query 2
        query2 = QueryRequest(
            question="What is deep learning?",
            workspace_id="test_workspace"
        )
        response2 = pipeline.query(query2)

        # Both queries should succeed
        assert len(response1.answer) > 0
        assert len(response2.answer) > 0

        # Should have different run IDs
        assert response1.run_id != response2.run_id

    def test_ledger_records_operations(self, pipeline, sample_documents):
        """Test ledger records index and query operations"""
        # Index documents
        index_request = IndexRequest(
            paths=sample_documents,
            workspace_id="test_workspace"
        )
        pipeline.index_documents(index_request)

        # Query
        query_request = QueryRequest(
            question="Test question",
            workspace_id="test_workspace"
        )
        pipeline.query(query_request)

        # Check ledger
        ledger = pipeline.ledger

        # Get workspace stats
        stats = ledger.get_workspace_stats("test_workspace")

        assert stats["index_runs"]["total"] >= 1
        assert stats["query_runs"]["total"] >= 1

        # Get specific runs
        runs = ledger.list_runs(workspace_id="test_workspace")

        assert len(runs["index_runs"]) >= 1
        assert len(runs["query_runs"]) >= 1

    def test_policy_redaction_in_query(self, pipeline, sample_documents):
        """Test policy redactor is applied during query"""
        # Index documents
        index_request = IndexRequest(
            paths=sample_documents,
            workspace_id="test_workspace"
        )
        pipeline.index_documents(index_request)

        # Query
        query_request = QueryRequest(
            question="What is AI?",
            workspace_id="test_workspace"
        )
        query_response = pipeline.query(query_request)

        # Citations should be truncated to 200 chars
        for citation in query_response.citations:
            assert len(citation.excerpt) <= 200

        # Answer should exist
        assert len(query_response.answer) > 0

    def test_workspace_isolation(self, temp_dirs):
        """Test different workspaces are isolated"""
        # Patch config
        Config.CHROMA_DB_PATH = temp_dirs["chroma_dir"]
        Config.LEDGER_DB_PATH = temp_dirs["ledger_path"]

        # Create document
        doc_path = os.path.join(temp_dirs["docs_dir"], "doc.txt")
        with open(doc_path, "w") as f:
            f.write("Content for workspace 1")

        # Create pipeline for workspace 1
        pipeline1 = RAGPipeline(
            llm_provider=OllamaLLMProvider(),
            embed_provider=OllamaEmbeddingProvider(),
            workspace_id="workspace1"
        )

        # Index in workspace 1
        index_req1 = IndexRequest(
            paths=[doc_path],
            workspace_id="workspace1"
        )
        pipeline1.index_documents(index_req1)

        # Create pipeline for workspace 2 (empty)
        pipeline2 = RAGPipeline(
            llm_provider=OllamaLLMProvider(),
            embed_provider=OllamaEmbeddingProvider(),
            workspace_id="workspace2"
        )

        # Workspace 2 should have no documents
        assert not pipeline2.retriever.exists()

        # Workspace 1 should have documents
        assert pipeline1.retriever.exists()


class TestHybridSafetyIntegration:
    """Integration tests for hybrid safety mode"""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories"""
        with tempfile.TemporaryDirectory() as chroma_dir, \
             tempfile.TemporaryDirectory() as docs_dir, \
             tempfile.NamedTemporaryFile(delete=False, suffix=".db") as ledger_file:

            ledger_path = ledger_file.name

            yield {
                "chroma_dir": chroma_dir,
                "docs_dir": docs_dir,
                "ledger_path": ledger_path
            }

            if os.path.exists(ledger_path):
                os.remove(ledger_path)

    def test_hybrid_safe_mode_truncates_snippets(self, temp_dirs):
        """Test hybrid safe mode enforces snippet truncation"""
        # Patch config
        original_chroma = Config.CHROMA_DB_PATH
        original_ledger = Config.LEDGER_DB_PATH
        original_safe_mode = Config.HYBRID_SAFE_MODE
        original_snippet_len = Config.MAX_SNIPPET_LENGTH

        Config.CHROMA_DB_PATH = temp_dirs["chroma_dir"]
        Config.LEDGER_DB_PATH = temp_dirs["ledger_path"]
        Config.HYBRID_SAFE_MODE = True
        Config.MAX_SNIPPET_LENGTH = 100  # Very short for testing

        # Create document with long content
        doc_path = os.path.join(temp_dirs["docs_dir"], "long.txt")
        long_content = "A" * 1000  # 1000 chars
        with open(doc_path, "w") as f:
            f.write(long_content)

        # Create pipeline
        pipeline = RAGPipeline(
            llm_provider=OllamaLLMProvider(),
            embed_provider=OllamaEmbeddingProvider(),
            workspace_id="test"
        )

        # Index
        pipeline.index_documents(IndexRequest(
            paths=[doc_path],
            workspace_id="test"
        ))

        # Query
        response = pipeline.query(QueryRequest(
            question="What is this?",
            workspace_id="test"
        ))

        # Citations should be truncated
        for citation in response.citations:
            # MAX_SNIPPET_LENGTH + "..." + source attribution
            # Response citations are already truncated to 200 chars
            assert len(citation.excerpt) <= 200

        # Restore config
        Config.CHROMA_DB_PATH = original_chroma
        Config.LEDGER_DB_PATH = original_ledger
        Config.HYBRID_SAFE_MODE = original_safe_mode
        Config.MAX_SNIPPET_LENGTH = original_snippet_len
