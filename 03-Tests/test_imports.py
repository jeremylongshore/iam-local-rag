"""Smoke test: the nexus package and its core modules import cleanly."""


def test_nexus_package_imports():
    import nexus  # noqa: F401
    from nexus.core import (  # noqa: F401
        config,
        ledger,
        models,
        policy,
        rag_pipeline,
        router,
    )


def test_api_app_imports():
    from nexus.api.server import app

    assert app is not None
