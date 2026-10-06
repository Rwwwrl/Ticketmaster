import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.exception_handlers import statement_timeout_exception_handler
from libs.fastapi_ext.middlewares import UnhandledExceptionMiddleware
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine]:
    test_engine = create_async_engine(url=os.environ["POSTGRES_DIRECT_DB_URL"])
    yield test_engine
    await test_engine.dispose()


@pytest.fixture(scope="session")
def router(engine: AsyncEngine) -> APIRouter:
    test_router = APIRouter()

    @test_router.get("/statement-timeout")
    async def statement_timeout_endpoint() -> None:
        async with engine.begin() as connection:
            await connection.execute(statement=text("SET LOCAL statement_timeout = '10ms'"))
            await connection.execute(statement=text("SELECT pg_sleep(1)"))

    @test_router.get("/other-db-error")
    async def other_db_error_endpoint() -> None:
        async with engine.begin() as connection:
            await connection.execute(statement=text("SELECT 1 / 0"))

    return test_router


@pytest.fixture(scope="session")
def app(router: APIRouter) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(UnhandledExceptionMiddleware)
    test_app.add_exception_handler(DBAPIError, statement_timeout_exception_handler)
    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_statement_timeout_exception_handler_when_statement_times_out_returns_504(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(url="/statement-timeout")

    assert response.status_code == 504
    assert response.json() == {"detail": "The server took too long to respond. Please retry later."}


@pytest.mark.asyncio(loop_scope="session")
async def test_statement_timeout_exception_handler_when_other_db_error_falls_through_to_500(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(url="/other-db-error")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
