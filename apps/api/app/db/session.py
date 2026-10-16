from collections.abc import AsyncIterator
from math import ceil

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.config import Settings


def connection_options(settings: Settings) -> dict:
    return {
        # libpq 的连接超时最小有效值为 2 秒；应用层另有更严格的总超时。
        "connect_timeout": max(2, ceil(settings.database_timeout_seconds)),
        "options": f"-c statement_timeout={ceil(settings.database_timeout_seconds * 1000)}",
    }


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        connect_args=connection_options(settings),
        pool_size=5,
        max_overflow=0,
        pool_timeout=settings.database_timeout_seconds,
        pool_pre_ping=True,
        hide_parameters=True,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session
