import logging
import re
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.exceptions import HTTPException

from app.api.health import router
from app.core.config import Settings
from app.core.errors import ErrorResponse, error_response
from app.core.logging import configure_logging
from app.db.session import create_database_engine

logger = logging.getLogger("agentradar")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database_engine(settings)
        application.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="AgentRadar API",
        version="0.0.0",
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    app.state.settings = settings

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 422, "VALIDATION_ERROR", "请求参数不符合要求。")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        messages = {404: "请求的资源不存在。", 405: "请求方法不受支持。"}
        response = error_response(
            request,
            exc.status_code,
            f"HTTP_{exc.status_code}",
            messages.get(exc.status_code, "请求无法完成。"),
        )
        response.headers.update(exc.headers or {})
        return response

    # 放在 CORS 内层，把未处理错误转为响应，使 500 响应也携带允许的跨域响应头。
    @app.middleware("http")
    async def handle_internal_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.error(
                "internal_error",
                extra={"request_id": request.state.request_id, "error_type": type(exc).__name__},
            )
            return error_response(request, 500, "INTERNAL_ERROR", "服务暂时无法完成请求。")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["X-Request-ID"],
        expose_headers=["X-Request-ID"],
        allow_credentials=False,
    )

    # 最外层先分配请求 ID，包含 CORS 预检；所有完成日志与响应共享该 ID。
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", incoming) else str(uuid4())
        request.state.request_id = request_id
        started = time.monotonic()
        response = await call_next(request)
        if request.method == "OPTIONS" and response.status_code == 400:
            # CORS 预检拒绝由中间件直接返回，也纳入统一错误约定。
            cors_headers = dict(response.headers)
            cors_headers.pop("content-length", None)
            cors_headers.pop("content-type", None)
            response = error_response(request, 400, "CORS_REJECTED", "跨域请求不被允许。")
            response.headers.update(cors_headers)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return response

    app.include_router(router, prefix="/api/v1")
    return app
