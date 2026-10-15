from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libs.aws.session import aws_session
from libs.fastapi_ext.middlewares import RequestIdMiddleware
from libs.sqlmodel_ext import BaseSqlModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine
from ticketmaster.admin.http.routes import admin_router
from ticketmaster.http.v1.routes import v1_router
from ticketmaster.models import Event, OutboxMessage, Ticket, User
from ticketmaster.settings import Settings
from ticketmaster.settings import settings as ticketmaster_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return ticketmaster_settings


@pytest.fixture(scope="session")
def autocleared_sqlmodel_tables() -> list[type[BaseSqlModel]]:
    return [Ticket, User, Event, OutboxMessage]


@pytest_asyncio.fixture(scope="session")
async def fastapi_app(sqlmodel_primary_engine: AsyncEngine, redis: Redis) -> AsyncGenerator[FastAPI]:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.state.sqlmodel_primary_engine = sqlmodel_primary_engine
    app.state.redis = redis
    app.include_router(router=v1_router, prefix="/api/v1")
    app.include_router(router=admin_router, prefix="/api/admin")
    yield app


@pytest_asyncio.fixture(scope="session")
async def async_client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def _mock_aws_client(monkeypatch: pytest.MonkeyPatch, client: AsyncMock) -> AsyncMock:
    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=client)
    context_manager.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(aws_session, "client", MagicMock(return_value=context_manager))
    return client


@pytest.fixture
def mock_s3(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    return _mock_aws_client(monkeypatch=monkeypatch, client=AsyncMock())


@pytest.fixture
def mock_cognito(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    cognito = AsyncMock()
    cognito.exceptions.UserNotFoundException = type("UserNotFoundException", (Exception,), {})
    return _mock_aws_client(monkeypatch=monkeypatch, client=cognito)
