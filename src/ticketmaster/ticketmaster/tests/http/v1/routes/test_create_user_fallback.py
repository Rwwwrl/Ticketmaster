"""Endpoint contract tests for POST /v1/users/. Auth dependency is bypassed via dependency_overrides;
JWT validation has its own coverage in test_dependencies.py."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from ticketmaster.http.v1.dependencies import validate_lambda_jwt


@pytest.fixture
def bypass_lambda_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    fastapi_app.dependency_overrides[validate_lambda_jwt] = lambda: None
    yield
    fastapi_app.dependency_overrides.clear()


def _payload() -> dict[str, Any]:
    return {
        "uuid": str(uuid4()),
        "email": "alice@example.com",
        "cognito_username": "alice@example.com",
        "pool_id": "eu-central-1_aB12cDEFg",
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_create_user_fallback_when_valid_payload_returns_201(
    async_client: AsyncClient, bypass_lambda_jwt: None
) -> None:
    payload = _payload()

    response = await async_client.post(url="/v1/users/", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["uuid"] == payload["uuid"]
    assert body["email"] == payload["email"]
    assert body["cognito_username"] == payload["cognito_username"]
    assert body["pool_id"] == payload["pool_id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_user_fallback_when_invalid_email_returns_422(
    async_client: AsyncClient, bypass_lambda_jwt: None
) -> None:
    response = await async_client.post(url="/v1/users/", json={**_payload(), "email": "not-an-email"})

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_create_user_fallback_when_duplicate_email_returns_400(
    async_client: AsyncClient, bypass_lambda_jwt: None
) -> None:
    payload = _payload()
    first = await async_client.post(url="/v1/users/", json=payload)
    assert first.status_code == 201

    second_payload = {**payload, "uuid": str(uuid4()), "cognito_username": "bob@example.com"}
    second = await async_client.post(url="/v1/users/", json=second_payload)

    assert second.status_code == 400
    assert "already exists" in second.json()["detail"]


@pytest.mark.asyncio(loop_scope="session")
async def test_create_user_fallback_when_duplicate_pool_cognito_username_returns_400(
    async_client: AsyncClient, bypass_lambda_jwt: None
) -> None:
    payload = _payload()
    first = await async_client.post(url="/v1/users/", json=payload)
    assert first.status_code == 201

    second_payload = {**payload, "uuid": str(uuid4()), "email": "other@example.com"}
    second = await async_client.post(url="/v1/users/", json=second_payload)

    assert second.status_code == 400
