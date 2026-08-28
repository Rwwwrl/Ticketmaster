from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from hello_world.main import health_check, readiness_check
from hello_world.main import hello_world as hello_world_endpoint
from hello_world.models import Visit
from hello_world.settings import Settings
from hello_world.settings import settings as hello_world_settings
from httpx import ASGITransport, AsyncClient
from libs.sqlmodel_ext import BaseSqlModel
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(scope="session")
def settings() -> Settings:
    return hello_world_settings


@pytest.fixture(scope="session")
def autocleared_sqlmodel_tables() -> list[type[BaseSqlModel]]:
    return [Visit]


@pytest_asyncio.fixture(scope="session")
async def fastapi_app(sqlmodel_engine: AsyncEngine) -> AsyncGenerator[FastAPI]:
    app = FastAPI()
    app.state.sqlmodel_engine = sqlmodel_engine
    app.add_api_route(path="/health-check", endpoint=health_check, methods=["GET"])
    app.add_api_route(path="/readiness-check", endpoint=readiness_check, methods=["GET"])
    app.add_api_route(path="/hello-world", endpoint=hello_world_endpoint, methods=["GET"])
    yield app


@pytest_asyncio.fixture(scope="session")
async def async_client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
