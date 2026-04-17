from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.middlewares import UnhandledExceptionMiddleware


@pytest.fixture(scope="session")
def router() -> APIRouter:
    test_router = APIRouter()

    @test_router.get("/ok")
    async def ok_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @test_router.get("/fail")
    async def fail_endpoint() -> None:
        raise RuntimeError("boom")

    return test_router


@pytest.fixture(scope="session")
def app(router: APIRouter) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(UnhandledExceptionMiddleware)
    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_unhandled_exception_middleware_when_request_succeeds(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/ok")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio(loop_scope="session")
async def test_unhandled_exception_middleware_when_unhandled_exception(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/fail")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
