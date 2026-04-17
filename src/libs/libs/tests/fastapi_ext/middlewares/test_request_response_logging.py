import logging
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.fastapi_ext.middlewares import RequestResponseLoggingMiddleware


@pytest.fixture(scope="session")
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestResponseLoggingMiddleware)

    router = APIRouter()

    @router.get("/echo")
    async def echo_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/echo")
    async def echo_post_endpoint(payload: dict) -> dict:
        return payload

    @router.get("/health")
    async def health_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_request_response_logging_when_get_request_logs_request_and_response(
    async_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="middleware.request_response"):
        response = await async_client.get(url="/echo")

    assert response.status_code == 200

    messages = [record.getMessage() for record in caplog.records]
    assert any("Incoming request GET /echo" in message for message in messages)
    assert any("Response GET /echo 200" in message for message in messages)


@pytest.mark.asyncio(loop_scope="session")
async def test_request_response_logging_when_post_request_preserves_body(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(url="/echo", json={"hello": "world"})

    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


@pytest.mark.asyncio(loop_scope="session")
async def test_request_response_logging_when_sensitive_header_is_redacted(
    async_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="middleware.request_response"):
        await async_client.get(url="/echo", headers={"authorization": "Bearer secret-token"})

    incoming_records = [record for record in caplog.records if "Incoming request" in record.getMessage()]
    assert incoming_records
    headers = incoming_records[-1].http_headers
    assert headers["authorization"] == "[REDACTED]"


@pytest.mark.asyncio(loop_scope="session")
async def test_request_response_logging_when_health_path_is_skipped(
    async_client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="middleware.request_response"):
        response = await async_client.get(url="/health")

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert not any("/health" in message for message in messages)
