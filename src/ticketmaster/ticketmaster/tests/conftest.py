from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libs.sqlmodel_ext import BaseSqlModel
from sqlalchemy.ext.asyncio import AsyncEngine
from ticketmaster.http.v1 import v1_router
from ticketmaster.models import Event, Ticket, User
from ticketmaster.settings import Settings
from ticketmaster.settings import settings as ticketmaster_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return ticketmaster_settings


@pytest.fixture(scope="session")
def autocleared_sqlmodel_tables() -> list[type[BaseSqlModel]]:
    return [Ticket, User, Event]


@pytest_asyncio.fixture(scope="session")
async def fastapi_app(sqlmodel_engine: AsyncEngine) -> AsyncGenerator[FastAPI]:
    app = FastAPI()
    app.state.sqlmodel_engine = sqlmodel_engine
    app.include_router(router=v1_router, prefix="/v1")
    yield app


@pytest_asyncio.fixture(scope="session")
async def async_client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
