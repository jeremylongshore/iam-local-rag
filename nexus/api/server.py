"""
FastAPI server for headless NEXUS RAG operations.
Provides REST API for querying and indexing.
"""
import time

from fastapi import FastAPI, HTTPException
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

# Initialize FastAPI app
app = FastAPI(
    title="NEXUS RAG API",
    description="Headless RAG API for document intelligence",
    version="1.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        vector_store_ready=pipeline._vectorstore is not None,
        documents_indexed=0,  # TODO: track this
        uptime_seconds=time.time() - _start_time,
        metrics=PerformanceMetrics(
            cache_hit_rate=0.0,
            avg_query_latency_ms=0.0,
            total_queries=_query_count,
            memory_mb=0.0
        )
    )


@app.post("/query", response_model=QueryResponse)
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


@app.post("/index", response_model=IndexResult)
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


@app.get("/workspaces")
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


@app.post("/workspaces")
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

    # Initialize pipeline for workspace (creates chroma directory)
    pipeline = get_pipeline(workspace_id)

    return {
        "workspace_id": workspace_id,
        "status": "created",
        "chroma_path": pipeline.chroma_path
    }


@app.get("/runs")
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


@app.get("/runs/{run_id}")
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
