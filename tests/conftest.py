"""Test fixtures.

Unit tests (scoring, parsing, status, transcription) need no infra. The DB-backed
fixtures below (`schema`, `client`, `sync_db`) target a real Postgres+pgvector and
**skip cleanly** when one isn't reachable, so `pytest` is green out of the box and
the integration layer runs in CI / against the compose DB.

Point tests at a throwaway database via env before collection, e.g.:
    POSTGRES_HOST=localhost POSTGRES_DB=focusstream_test pytest
"""

import os

# Must be set before importing any app module (settings + engines bind at import).
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "focusstream_test")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.fixture(scope="session")
def pg_available() -> bool:
    """True if a Postgres with the vector extension is reachable."""
    try:
        from app.core.database import sync_engine

        with sync_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        return True
    except Exception:
        return False


@pytest.fixture
def schema(pg_available):
    """Fresh schema per test."""
    if not pg_available:
        pytest.skip("Postgres+pgvector unavailable — set POSTGRES_* env to run integration tests")
    from app.core.database import sync_engine
    from app.models import Base

    Base.metadata.drop_all(sync_engine)
    Base.metadata.create_all(sync_engine)
    yield
    Base.metadata.drop_all(sync_engine)


@pytest.fixture(autouse=True)
def stub_celery(monkeypatch):
    """Replace every task's .delay with a MagicMock so no broker is needed and
    dispatches can be asserted. No-op if the worker modules can't import."""
    try:
        from app.workers import ingestion, tasks
    except Exception:
        return
    for task in (
        tasks.embed_sprint_intent,
        tasks.embed_content_item,
        tasks.match_item_to_sprints,
        ingestion.poll_all_sources,
        ingestion.poll_source,
        ingestion.transcribe_podcast,
    ):
        monkeypatch.setattr(task, "delay", MagicMock())


@pytest_asyncio.fixture
async def client(schema):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sync_db(schema):
    """A sync session (same DB the async request path uses) for seeding rows and
    driving Celery task functions directly."""
    from app.core.database import SyncSessionLocal

    with SyncSessionLocal() as db:
        yield db


def vec(dim: int, first: float = 1.0) -> list[float]:
    """A unit-ish vector: [first, 0, 0, ...]."""
    v = [0.0] * dim
    v[0] = first
    return v
