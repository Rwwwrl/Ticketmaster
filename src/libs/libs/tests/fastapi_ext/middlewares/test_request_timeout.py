import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.middlewares import RequestTimeoutMiddleware

_TIMEOUT_SECONDS = 0.05


@pytest.fixture(scope="session")
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=_TIMEOUT_SECONDS)

    router = APIRouter()

    @router.get("/fast")
    async def fast_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/slow")
    async def slow_endpoint() -> dict[str, str]:
        await asyncio.sleep(_TIMEOUT_SECONDS * 10)
        return {"status": "ok"}

    @router.get("/streaming")
    async def streaming_endpoint() -> StreamingResponse:
        async def body() -> AsyncGenerator[bytes]:
            yield b"chunk"
            await asyncio.sleep(_TIMEOUT_SECONDS * 10)
            yield b"more"

        return StreamingResponse(content=body())

    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_request_timeout_when_fast_endpoint(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/fast")

    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_request_timeout_when_slow_endpoint(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/slow")

    assert response.status_code == 504
    assert response.json() == {"detail": "Request timed out"}


@pytest.mark.asyncio(loop_scope="session")
async def test_request_timeout_when_streaming_response_already_started(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/streaming")

    assert response.status_code == 200
