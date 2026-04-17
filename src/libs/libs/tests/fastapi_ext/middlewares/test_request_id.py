import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from libs.context_vars import request_id_var
from libs.fastapi_ext.consts import REQUEST_ID_HEADER
from libs.fastapi_ext.middlewares import RequestIdMiddleware


@pytest.fixture(scope="session")
def router() -> APIRouter:
    test_router = APIRouter()

    @test_router.get("/echo-request-id")
    async def echo_request_id() -> dict[str, str | None]:
        return {"request_id": request_id_var.get()}

    return test_router


@pytest.fixture(scope="session")
def app(router: APIRouter) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)
    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_middleware_when_no_header(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/echo-request-id")

    assert response.status_code == 200
    response_request_id = response.headers[REQUEST_ID_HEADER]
    uuid.UUID(response_request_id, version=4)

    body = response.json()
    assert body["request_id"] == response_request_id


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_middleware_when_header_provided(async_client: AsyncClient) -> None:
    provided_id = str(uuid.uuid4())
    response = await async_client.get(url="/echo-request-id", headers={REQUEST_ID_HEADER: provided_id})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == provided_id

    body = response.json()
    assert body["request_id"] == provided_id


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_middleware_when_valid_non_uuid_format(async_client: AsyncClient) -> None:
    provided_id = "trace-abc-123"
    response = await async_client.get(url="/echo-request-id", headers={REQUEST_ID_HEADER: provided_id})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == provided_id

    body = response.json()
    assert body["request_id"] == provided_id


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_middleware_when_overly_long_id(async_client: AsyncClient) -> None:
    long_id = "A" * 300
    response = await async_client.get(url="/echo-request-id", headers={REQUEST_ID_HEADER: long_id})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid X-Request-ID header"}


@pytest.mark.asyncio(loop_scope="session")
async def test_request_id_middleware_when_control_characters(async_client: AsyncClient) -> None:
    malicious_id = "request-id\x00injected"
    response = await async_client.get(url="/echo-request-id", headers={REQUEST_ID_HEADER: malicious_id})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid X-Request-ID header"}
