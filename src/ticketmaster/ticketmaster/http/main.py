from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from libs.common.enums import AppNameEnum, ServiceNameEnum
from libs.fastapi_ext.middlewares import (
    RequestBodyLimitMiddleware,
    RequestIdMiddleware,
    RequestResponseLoggingMiddleware,
    SecurityHeadersMiddleware,
    UnhandledExceptionMiddleware,
)
from libs.logging import setup_logging
from libs.logging.enums import ProcessTypeEnum
from libs.sentry_ext import setup_sentry
from libs.settings import is_data_sensitive_env
from libs.sqlmodel_ext import Session
from libs.sqlmodel_ext.utils import health_check as postgres_health_check

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
    setup_sentry(settings=settings, release=version("ticketmaster"))

    engine = init_sqlmodel_engine(db_url=settings.postgres_db_url)
    Session.configure(bind=engine)
    app.state.sqlmodel_engine = engine

    yield

    await engine.dispose()


_is_sensitive = is_data_sensitive_env(environment=settings.environment)

app = FastAPI(
    title="Ticketmaster",
    version=version("ticketmaster"),
    description="Ticketmaster monolith service.",
    lifespan=lifespan,
    docs_url=None if _is_sensitive else "/docs",
    redoc_url=None if _is_sensitive else "/redoc",
    openapi_url=None if _is_sensitive else "/openapi.json",
)

app.add_middleware(UnhandledExceptionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestResponseLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=1_048_576)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readiness_check")
async def readiness_check() -> dict[str, str]:
    await postgres_health_check()
    return {"status": "ok"}


app.include_router(router=v1_router, prefix="/v1")
