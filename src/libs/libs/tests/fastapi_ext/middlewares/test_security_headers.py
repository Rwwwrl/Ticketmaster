from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.middlewares import SecurityHeadersMiddleware


@pytest.fixture(scope="session")
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    router = APIRouter()

    @router.get("/test")
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
async def test_security_headers_middleware_when_success_adds_x_content_type_options(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/test")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio(loop_scope="session")
async def test_security_headers_middleware_when_success_adds_strict_transport_security(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(url="/test")

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains"


@pytest.mark.asyncio(loop_scope="session")
async def test_security_headers_middleware_when_error_response(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/nonexistent")

    assert response.status_code == 404
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Strict-Transport-Security"] == "max-age=63072000; includeSubDomains"
