"""
Smoke test for the Streamlit entry point (02-Src/app_nexus.py).

Parses the module without executing its top-level Streamlit code, and verifies
the nexus-core symbols it depends on are importable. The legacy apps this file
used to test (app.py / app_optimized.py) were archived to 99-Archive/.
"""
import ast
import pathlib

APP_NEXUS = pathlib.Path(__file__).parent.parent / "02-Src" / "app_nexus.py"


def test_app_nexus_parses():
    """app_nexus.py is valid Python (no execution of Streamlit calls)."""
    assert APP_NEXUS.exists()
    ast.parse(APP_NEXUS.read_text())


def test_app_nexus_core_dependencies_import():
    """The nexus-core symbols the shim imports resolve."""
    from nexus.core.config import Config, NexusMode
    from nexus.core.models import IndexRequest, QueryRequest
    from nexus.core.rag_pipeline import RAGPipeline
    from nexus.core.router import ProviderRouter

    assert RAGPipeline is not None
    assert ProviderRouter is not None
    assert Config is not None
    assert NexusMode is not None
    assert QueryRequest is not None
    assert IndexRequest is not None
