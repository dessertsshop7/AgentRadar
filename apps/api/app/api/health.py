import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.core.errors import ErrorDetail
from app.db.session import get_session

router = APIRouter()
logger = logging.getLogger("agentradar")


class DatabaseHealth(BaseModel):
    status: Literal["healthy", "unhealthy"]


class DependenciesHealth(BaseModel):
    database: DatabaseHealth


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: DependenciesHealth
    request_id: str
    error: ErrorDetail | None = None


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> JSONResponse:
    request_id = request.state.request_id
    try:
        async with asyncio.timeout(request.app.state.settings.database_timeout_seconds):
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, TimeoutError) as exc:
        logger.warning(
            "database_unavailable",
            extra={"request_id": request_id, "error_type": type(exc).__name__},
        )
        payload = HealthResponse(
            status="degraded",
            dependencies=DependenciesHealth(database=DatabaseHealth(status="unhealthy")),
            request_id=request_id,
            error=ErrorDetail(
                code="DATABASE_UNAVAILABLE", message="数据库暂时不可用，请稍后重试。"
            ),
        )
        status_code = 503
    else:
        payload = HealthResponse(
            status="ok",
            dependencies=DependenciesHealth(database=DatabaseHealth(status="healthy")),
            request_id=request_id,
        )
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True),
        headers={"Cache-Control": "no-store"},
    )
