import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app


class DatabaseSessionDouble:
    """仅用于单元测试：替代数据库 I/O，不代表 PostgreSQL 验证。"""

    def __init__(self, mode: str = "healthy") -> None:
        self.mode = mode

    async def execute(self, statement):
        if str(statement) != "SELECT 1":
            raise AssertionError("健康检查必须执行轻量数据库查询")
        if self.mode == "unhealthy":
            raise OperationalError("SELECT 1", {}, Exception("password=must-not-leak"))
        if self.mode == "slow":
            await asyncio.sleep(60)


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unit:unit@localhost:1/unit",
        database_timeout_seconds=0.1,
    )
    application = create_app(settings)

    @application.get("/api/v1/_test/validate")
    def validate(value: int) -> dict:
        return {"value": value}

    @application.get("/api/v1/_test/crash")
    def crash() -> None:
        raise RuntimeError("password=must-not-leak")

    return application


@pytest.fixture
def client_factory(app):
    def factory(mode: str = "healthy"):
        async def session_override() -> AsyncIterator[DatabaseSessionDouble]:
            yield DatabaseSessionDouble(mode)

        app.dependency_overrides[get_session] = session_override
        return TestClient(
            app,
            raise_server_exceptions=False,
            backend_options={"loop_factory": asyncio.SelectorEventLoop},
        )

    return factory


@pytest.fixture
def client(client_factory) -> Iterator[TestClient]:
    with client_factory() as test_client:
        yield test_client
