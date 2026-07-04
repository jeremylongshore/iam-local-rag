"""
Pydantic models for NEXUS RAG pipeline.
Defines data structures for requests, responses, and internal state.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentSource(BaseModel):
    """Metadata for a source document"""
    file_path: str
    file_hash: str
    file_mtime: float
    indexed_at: datetime


class DocumentChunk(BaseModel):
    """A chunk of text from a document with metadata"""
    content: str
    source: str
    page: Optional[int] = None
    chunk_index: int
    embedding_hash: Optional[str] = None


class Citation(BaseModel):
    """Citation information for a retrieved chunk"""
    source: str
    page: Optional[int] = None
    excerpt: str
    relevance_score: float
    content_hash: str  # Hash of the content (not full document)


class QueryRequest(BaseModel):
    """Request to query the knowledge base"""
    question: str = Field(..., min_length=1, max_length=5000)
    workspace_id: str = Field(default="default")
    mode: Optional[str] = None  # Override config mode if provided
    max_results: int = Field(default=3, ge=1, le=10)


class PrivacyReceipt(BaseModel):
    """
    Per-query privacy receipt (acceptance invariant #4). Answers, verifiably,
    "what left this machine?" for a single query.
    """
    mode: str
    llm_provider: str
    llm_model: Optional[str] = None
    llm_destination: str = "local"  # "local" | "cloud"
    embed_provider: str
    embed_destination: str = "local"
    chars_sent_to_cloud: int = 0
    tokens_sent_estimate: int = 0
    chunk_ids: List[str] = Field(default_factory=list)
    content_hashes: List[str] = Field(default_factory=list)
    redactions: List[Dict[str, Any]] = Field(default_factory=list)
    secret_patterns_detected: List[str] = Field(default_factory=list)
    policy_pass: bool = True


class QueryResponse(BaseModel):
    """Response from a knowledge base query"""
    question: str
    answer: str
    citations: List[Citation]
    workspace_id: str
    model_used: str
    provider: str
    latency_ms: float
    run_id: str
    timestamp: datetime
    privacy_receipt: Optional[PrivacyReceipt] = None


class IndexRequest(BaseModel):
    """Request to index documents"""
    paths: List[str]
    workspace_id: str = Field(default="default")
    force_reindex: bool = False


class IndexResult(BaseModel):
    """Result of document indexing operation"""
    workspace_id: str
    files_processed: int
    files_skipped: int
    total_chunks: int
    processing_time_ms: float
    document_sources: List[DocumentSource]


class PerformanceMetrics(BaseModel):
    """Performance metrics for monitoring"""
    cache_hit_rate: float
    avg_query_latency_ms: float
    total_queries: int
    memory_mb: float


class HealthStatus(BaseModel):
    """Health check status"""
    status: str  # "healthy", "degraded", "unhealthy"
    mode: str
    llm_provider: str
    embed_provider: str
    vector_store_ready: bool
    documents_indexed: int
    uptime_seconds: float
    metrics: PerformanceMetrics


class WorkspaceInfo(BaseModel):
    """Information about a workspace"""
    workspace_id: str
    document_count: int
    chunk_count: int
    created_at: datetime
    last_updated: datetime
    last_query_at: Optional[datetime] = None


class RunLedgerEntry(BaseModel):
    """Entry in the run ledger for audit trail"""
    run_id: str
    workspace_id: str
    timestamp: datetime
    operation: str  # "query" or "index"
    model_used: str
    provider: str
    document_hashes: List[str]  # Hashes of documents used
    excerpt_hashes: List[str]  # Hashes of excerpts sent to cloud (if hybrid/cloud)
    user_query_hash: Optional[str] = None  # Hash of user question
    latency_ms: float
    success: bool
    error_message: Optional[str] = None
