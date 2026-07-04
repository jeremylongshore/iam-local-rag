"""
FastAPI server for headless NEXUS RAG operations.
Provides REST API for querying and indexing.
"""
import logging
import secrets
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..core.config import Config
from ..core.ledger import RunLedger
from ..core.models import (
    HealthStatus,
    IndexRequest,
    IndexResult,
    PerformanceMetrics,
    QueryRequest,
    QueryResponse,
)
from ..core.rag_pipeline import RAGPipeline

logger = logging.getLogger("nexus.api")

# Initialize FastAPI app
app = FastAPI(
    title="NEXUS RAG API",
    description="Headless RAG API for document intelligence",
    version="1.1.0"
)

# CORS — allowlist from config (NOT wildcard by default; a "*" origin with an
# API this mutating is a drive-by/CSRF vector). allow_credentials only when the
# allowlist is explicit (browsers reject "*" + credentials anyway).
_cors_origins = Config.NEXUS_CORS_ORIGINS
_wildcard_cors = _cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=not _wildcard_cors,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)

if not Config.NEXUS_API_KEY:
    logger.warning(
        "NEXUS_API_KEY is not set — the API is UNAUTHENTICATED. Set NEXUS_API_KEY "
        "to require a key on /query, /index, /workspaces and /runs."
    )


async def require_api_key(
    authorization: str = Header(default=None),
    x_api_key: str = Header(default=None),
) -> None:
    """Require the configured API key on protected endpoints (no-op if unset)."""
    expected = Config.NEXUS_API_KEY
    if not expected:
        return  # auth disabled (local dev) — warned at startup
    presented = x_api_key
    if not presented and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:]
    # Constant-time compare to avoid a byte-by-byte timing oracle; guard the
    # empty/None case first (compare_digest requires two strings).
    if not presented or not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="missing or invalid API key")

# Global state
_pipelines = {}  # workspace_id -> RAGPipeline
_start_time = time.time()
_query_count = 0
_ledger = RunLedger()  # Global ledger instance


def get_pipeline(workspace_id: str = "default") -> RAGPipeline:
    """Get or create pipeline for workspace"""
    if workspace_id not in _pipelines:
        _pipelines[workspace_id] = RAGPipeline(workspace_id=workspace_id)
    return _pipelines[workspace_id]


@app.get("/health", response_model=HealthStatus)
async def health_check():
    """Health check endpoint"""
    global _query_count

    pipeline = get_pipeline()

    return HealthStatus(
        status="healthy",
        mode=Config.NEXUS_MODE.value,
        llm_provider=Config.NEXUS_LLM_PROVIDER.value,
        embed_provider=Config.NEXUS_EMBED_PROVIDER.value,
        vector_store_ready=pipeline.retriever.exists(),
        documents_indexed=0,  # TODO: track this
        uptime_seconds=time.time() - _start_time,
        metrics=PerformanceMetrics(
            cache_hit_rate=0.0,
            avg_query_latency_ms=0.0,
            total_queries=_query_count,
            memory_mb=0.0
        )
    )


@app.post("/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)])
async def query_knowledge_base(request: QueryRequest):
    """
    Query the knowledge base.

    Args:
        request: Query request with question and workspace_id

    Returns:
        QueryResponse with answer and citations
    """
    global _query_count

    try:
        pipeline = get_pipeline(request.workspace_id)
        response = pipeline.query(request)
        _query_count += 1
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/index", response_model=IndexResult, dependencies=[Depends(require_api_key)])
async def index_documents(request: IndexRequest):
    """
    Index documents into workspace.

    Args:
        request: Index request with file paths

    Returns:
        IndexResult with processing stats
    """
    try:
        pipeline = get_pipeline(request.workspace_id)
        result = pipeline.index_documents(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workspaces", dependencies=[Depends(require_api_key)])
async def list_workspaces():
    """
    List all active workspaces.

    Returns:
        List of workspace IDs with basic stats
    """
    import os

    workspaces = []

    # Get workspace IDs from Chroma directories
    chroma_base = Config.CHROMA_DB_PATH
    if os.path.exists(chroma_base):
        for workspace_id in os.listdir(chroma_base):
            workspace_path = os.path.join(chroma_base, workspace_id)
            if os.path.isdir(workspace_path):
                # Get stats from ledger
                stats = _ledger.get_workspace_stats(workspace_id)
                workspaces.append({
                    "workspace_id": workspace_id,
                    "stats": stats
                })

    return {
        "workspaces": workspaces,
        "total": len(workspaces)
    }


@app.post("/workspaces", dependencies=[Depends(require_api_key)])
async def create_workspace(workspace_id: str):
    """
    Create a new workspace.

    Args:
        workspace_id: ID for the new workspace

    Returns:
        Workspace creation confirmation
    """
    if not workspace_id or workspace_id == "":
        raise HTTPException(status_code=400, detail="workspace_id is required")

    # Validate the slug BEFORE it is ever used as a path component (defense in
    # depth; the pipeline also validates, but reject early with a clean 400).
    from ..core.rag_pipeline import _safe_workspace_id

    try:
        _safe_workspace_id(workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Initialize pipeline for workspace and persist its directory so the
    # workspace is listable before any documents are indexed.
    pipeline = get_pipeline(workspace_id)
    import os

    os.makedirs(pipeline.workspace_dir, exist_ok=True)

    return {
        "workspace_id": workspace_id,
        "status": "created",
        "chroma_path": pipeline.chroma_path
    }


@app.get("/runs", dependencies=[Depends(require_api_key)])
async def list_runs(
    workspace_id: str = None,
    run_type: str = "all",
    limit: int = 100
):
    """
    List runs from the ledger.

    Args:
        workspace_id: Filter by workspace (optional)
        run_type: "index", "query", or "all"
        limit: Max runs to return (default 100)

    Returns:
        Dict with index_runs and query_runs lists
    """
    try:
        runs = _ledger.list_runs(
            workspace_id=workspace_id,
            run_type=run_type,
            limit=limit
        )
        return runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", dependencies=[Depends(require_api_key)])
async def get_run(run_id: str):
    """
    Get details for a specific run.

    Args:
        run_id: Run ID to fetch

    Returns:
        Run details or 404
    """
    run = _ledger.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.get("/audit/verify", dependencies=[Depends(require_api_key)])
async def audit_verify():
    """Verify the tamper-evident audit hash-chain. Returns {ok, total, breaks}."""
    return _ledger.verify_chain()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "NEXUS RAG API",
        "version": "1.1.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "query": "POST /query",
            "index": "POST /index",
            "workspaces": "GET /workspaces",
            "create_workspace": "POST /workspaces?workspace_id=<id>",
            "runs": "GET /runs",
            "run_details": "GET /runs/{run_id}"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=Config.API_HOST,
        port=Config.API_PORT,
        workers=Config.API_WORKERS
    )
