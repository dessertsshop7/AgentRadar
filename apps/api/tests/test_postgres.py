"""真实 PostgreSQL 集成验证；不使用 SQLite、Session 替身或伪造迁移结果。"""

import asyncio
import os
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def database_url():
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("未设置 TEST_DATABASE_URL，未执行真实 PostgreSQL 验证")
    assert make_url(value).drivername == "postgresql+psycopg"
    return value


def test_baseline_migration_is_recorded_and_repeatable(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_engine(database_url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "0001_p00_baseline"
    finally:
        engine.dispose()


def test_health_queries_real_postgres(database_url):
    settings = Settings(_env_file=None, database_url=database_url)
    with TestClient(
        create_app(settings), backend_options={"loop_factory": asyncio.SelectorEventLoop}
    ) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dependencies"]["database"]["status"] == "healthy"
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_real_connection_refusal_returns_503_within_timeout(database_url):
    # 连接本机关闭的端口，触发真实驱动错误；不停止其他应用的数据库。
    refused_url = make_url(database_url).set(host="127.0.0.1", port=1)
    settings = Settings(
        _env_file=None,
        database_url=refused_url.render_as_string(hide_password=False),
        database_timeout_seconds=0.5,
    )
    with TestClient(
        create_app(settings), backend_options={"loop_factory": asyncio.SelectorEventLoop}
    ) as client:
        started = time.monotonic()
        response = client.get("/api/v1/health")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert response.json()["dependencies"]["database"]["status"] == "unhealthy"
    assert elapsed < 3
    assert "agentradar_dev_only" not in response.text
