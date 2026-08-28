from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from libs.aws.session import bind_task_role_to_aws_session
from libs.common.enums import AppNameEnum, ServiceNameEnum
from libs.fastapi_ext.middlewares import (
    RequestBodyLimitMiddleware,
    RequestIdMiddleware,
    RequestResponseLoggingMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
    UnhandledExceptionMiddleware,
)
from libs.logging import setup_logging
from libs.logging.enums import ProcessTypeEnum
from libs.redis_ext import redis_proxy
from libs.redis_ext.utils import health_check as redis_health_check
from libs.sentry_ext import setup_sentry
from libs.settings import is_data_sensitive_env
from libs.sqlmodel_ext import Session
from libs.sqlmodel_ext.utils import health_check as postgres_health_check
from redis.asyncio import Redis

from ticketmaster.admin.http.routes import admin_router
from ticketmaster.http.v1.routes import v1_router
from ticketmaster.settings import settings
from ticketmaster.utils import init_sqlmodel_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(
        settings=settings,
        app_name=AppNameEnum.TICKETMASTER,
        service_name=ServiceNameEnum.TICKETMASTER,
        process_type=ProcessTypeEnum.FASTAPI,
    )
    setup_sentry(settings=settings, release=settings.version)

    engine = init_sqlmodel_engine(db_url=settings.postgres_db_url)
    Session.configure(bind=engine)
    app.state.sqlmodel_engine = engine

    redis_proxy.configure_with_client(client=Redis.from_url(url=settings.redis_url, decode_responses=False))
    app.state.redis = redis_proxy.redis

    if settings.aws_task_role is not None:
        bind_task_role_to_aws_session(
            region=settings.aws_task_role.region,
            access_key_id=settings.aws_task_role.access_key_id,
            secret_access_key=settings.aws_task_role.secret_access_key,
            session_token=settings.aws_task_role.session_token,
        )

    yield

    await redis_proxy.redis.aclose()
    await engine.dispose()


_is_sensitive = is_data_sensitive_env(environment=settings.environment)

app = FastAPI(
    title="Ticketmaster",
    version=settings.version,
    description="Ticketmaster monolith service.",
    lifespan=lifespan,
    docs_url=None if _is_sensitive else "/api/docs",
    redoc_url=None if _is_sensitive else "/api/redoc",
    openapi_url=None if _is_sensitive else "/api/openapi.json",
)

app.add_middleware(UnhandledExceptionMiddleware)
app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=10)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestResponseLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=1_048_576)


@app.get("/health-check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness-check")
async def readiness_check() -> dict[str, str]:
    await postgres_health_check()
    await redis_health_check()
    return {"status": "ok"}


app.include_router(router=v1_router, prefix="/api/v1")
app.include_router(router=admin_router, prefix="/api/admin")
