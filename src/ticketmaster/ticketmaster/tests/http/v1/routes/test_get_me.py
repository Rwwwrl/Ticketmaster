"""Endpoint contract tests for GET /api/v1/me/. Auth dependency is bypassed via dependency_overrides;
JWT validation has its own coverage in test_dependencies.py."""

from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from ticketmaster.http.v1.dependencies import validate_user_jwt
from ticketmaster.schemas.dtos import BaseUserDTO


def _dto() -> BaseUserDTO:
    return BaseUserDTO(
        id=1,
        uuid=uuid4(),
        pool_id="eu-central-1_aB12cDEFg",
        email="alice@example.com",
        cognito_username="alice@example.com",
        created_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 22, tzinfo=timezone.utc),
    )


@pytest.fixture
def signed_in_user(fastapi_app: FastAPI) -> Iterator[BaseUserDTO]:
    dto = _dto()
    fastapi_app.dependency_overrides[validate_user_jwt] = lambda: dto
    yield dto
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_me_when_signed_in_returns_200(
    async_client: AsyncClient,
    signed_in_user: BaseUserDTO,
) -> None:
    response = await async_client.get(url="/api/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 200
    body = response.json()
    assert body["uuid"] == str(signed_in_user.uuid)
    assert body["email"] == signed_in_user.email
    assert body["pool_id"] == signed_in_user.pool_id
    assert body["cognito_username"] == signed_in_user.cognito_username


@pytest.mark.asyncio(loop_scope="session")
async def test_get_me_when_missing_authorization_header_returns_422(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(url="/api/v1/me/")

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_get_me_when_invalid_jwt_returns_401(
    async_client: AsyncClient,
    invalid_jwt: None,
) -> None:
    response = await async_client.get(url="/api/v1/me/", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
