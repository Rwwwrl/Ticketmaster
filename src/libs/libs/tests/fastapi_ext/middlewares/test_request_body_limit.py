from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.middlewares import RequestBodyLimitMiddleware


@pytest.fixture(scope="session")
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestBodyLimitMiddleware, max_body_size=1024)

    router = APIRouter()

    @router.post("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_request_body_limit_when_within_limit(async_client: AsyncClient) -> None:
    response = await async_client.post(url="/test", content=b"x" * 512)

    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_request_body_limit_when_exceeding_limit(async_client: AsyncClient) -> None:
    response = await async_client.post(
        url="/test",
        content=b"x" * 2048,
        headers={"content-length": "2048"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


@pytest.mark.asyncio(loop_scope="session")
async def test_request_body_limit_when_no_content_length(async_client: AsyncClient) -> None:
    response = await async_client.post(url="/test")

    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_request_body_limit_when_at_exact_limit(async_client: AsyncClient) -> None:
    response = await async_client.post(
        url="/test",
        content=b"x" * 1024,
        headers={"content-length": "1024"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_request_body_limit_when_oversized_body_without_content_length(async_client: AsyncClient) -> None:
    response = await async_client.post(url="/test", content=b"x" * 2048)

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
