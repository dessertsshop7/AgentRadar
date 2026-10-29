import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
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


@pytest.fixture
def database_url():
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("未设置 TEST_DATABASE_URL，未执行真实 PostgreSQL 验证")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL 必须指向名称以 _test 结尾的独立 PostgreSQL 测试库")
    return value


@pytest.fixture
def pg(database_url, monkeypatch):
    """只在显式指定的独立测试库中迁移及清理 P02 表。"""
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url, connect_args={"connect_timeout": 3}, hide_parameters=True)
    with engine.begin() as connection:
        assert (
            connection.scalar(text("SELECT current_database()")) == make_url(database_url).database
        )
        from app.db.base import Base

        tables = sorted(set(inspect(connection).get_table_names()) & set(Base.metadata.tables))
        # 表名来自本测试库的元信息；连接目标已校验，不对开发库执行清理。
        if tables:
            names = ", ".join('"' + name.replace('"', '""') + '"' for name in tables)
            connection.exec_driver_sql(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def asset_client(pg, database_url):
    application = create_app(Settings(_env_file=None, database_url=database_url))
    with TestClient(
        application, backend_options={"loop_factory": asyncio.SelectorEventLoop}
    ) as client:
        yield client
