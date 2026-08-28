import hashlib

import pytest
from hello_world.schemas.response_schemas import HelloWorldResponseSchema
from hello_world.settings import settings
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_health_check_returns_ok(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/health-check")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio(loop_scope="session")
async def test_readiness_check_when_database_reachable_returns_ok(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/readiness-check")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio(loop_scope="session")
async def test_hello_world_returns_fingerprint_and_increments_visit_count(async_client: AsyncClient) -> None:
    first = await async_client.get(url="/hello-world")
    second = await async_client.get(url="/hello-world")

    first_body = HelloWorldResponseSchema(**first.json())
    second_body = HelloWorldResponseSchema(**second.json())

    assert first_body.environment == settings.environment
    assert first_body.secret_fingerprint == hashlib.sha256(settings.secret.encode()).hexdigest()[:8]
    assert second_body.visit_count == first_body.visit_count + 1
