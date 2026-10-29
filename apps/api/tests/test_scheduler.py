import asyncio
import threading

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_scheduler_is_disabled_by_default_and_never_starts_external_sync(monkeypatch):
    from app.ingestion.sync import SyncService

    called = []

    async def tick(self):
        called.append(True)

    monkeypatch.setattr(SyncService, "tick", tick)
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://unit:unit@localhost:1/unit"
    )
    with TestClient(
        create_app(settings), backend_options={"loop_factory": asyncio.SelectorEventLoop}
    ):
        assert called == []


def test_enabled_scheduler_performs_startup_check_without_blocking_app(monkeypatch):
    from app.ingestion.sync import SyncService

    entered = threading.Event()

    async def tick(self):
        entered.set()

    monkeypatch.setattr(SyncService, "tick", tick)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unit:unit@localhost:1/unit",
        sync_enabled=True,
        github_token="test-only",
    )
    with TestClient(
        create_app(settings), backend_options={"loop_factory": asyncio.SelectorEventLoop}
    ):
        assert entered.wait(2)
