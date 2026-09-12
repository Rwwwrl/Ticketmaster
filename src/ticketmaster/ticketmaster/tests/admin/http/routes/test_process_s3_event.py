"""Endpoint contract tests for POST /api/admin/s3-events. The lambda JWT dependency is bypassed
via dependency_overrides, same pattern as bypass_admin_jwt in tests/admin/http/conftest.py."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from sqlmodel import select
from ticketmaster.admin.http.dependencies import validate_s3_events_lambda_jwt
from ticketmaster.models import Event
from ticketmaster.redis_cache.repositories import NamespaceRepository
from ticketmaster.tests.factories import EventFactory

_BUCKET = "ticketmaster-test-eu-media-public"


@pytest.fixture
def bypass_s3_events_lambda_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    fastapi_app.dependency_overrides[validate_s3_events_lambda_jwt] = lambda: None
    yield
    fastapi_app.dependency_overrides.clear()


def _payload(key: str, metadata: dict[str, str], bucket: str = _BUCKET) -> dict:
    return {"bucket": bucket, "key": key, "metadata": metadata}


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_event_trailer_persists_trailer_fields(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    event = EventFactory()
    await insert(event)
    key = "event-trailer/9f3cd1.mp4"

    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(key=key, metadata={"kind": "event-trailer", "logical-identity": str(event.logical_identity)}),
    )

    assert response.status_code == 204

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == event.id))).one()
        assert persisted.trailer_bucket == _BUCKET
        assert persisted.trailer_key == key


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_rotates_list_events_page_namespace(
    async_client: AsyncClient, redis: Redis, bypass_s3_events_lambda_jwt: None
) -> None:
    event = EventFactory()
    await insert(event)
    previous_namespace = await NamespaceRepository.set(redis=redis)

    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(
            key="event-trailer/a.mp4",
            metadata={"kind": "event-trailer", "logical-identity": str(event.logical_identity)},
        ),
    )
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 204
    assert current_namespace is not None
    assert current_namespace != previous_namespace


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_kind_missing_is_a_noop(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    event = EventFactory()
    await insert(event)

    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(key="event-trailer/a.mp4", metadata={"logical-identity": str(event.logical_identity)}),
    )

    assert response.status_code == 204

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == event.id))).one()
        assert persisted.trailer_bucket == event.trailer_bucket
        assert persisted.trailer_key == event.trailer_key


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_kind_unknown_is_a_noop(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    event = EventFactory()
    await insert(event)

    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(
            key="avatars/1/x.png",
            metadata={"kind": "avatar", "logical-identity": str(event.logical_identity)},
        ),
    )

    assert response.status_code == 204

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == event.id))).one()
        assert persisted.trailer_bucket == event.trailer_bucket
        assert persisted.trailer_key == event.trailer_key


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_logical_identity_missing_returns_422(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(key="event-trailer/a.mp4", metadata={"kind": "event-trailer"}),
    )

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_logical_identity_not_a_uuid_returns_422(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(key="event-trailer/a.mp4", metadata={"kind": "event-trailer", "logical-identity": "not-a-uuid"}),
    )

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_process_s3_event_when_logical_identity_unknown_returns_404(
    async_client: AsyncClient, bypass_s3_events_lambda_jwt: None
) -> None:
    response = await async_client.post(
        url="/api/admin/s3-events",
        json=_payload(
            key="event-trailer/a.mp4",
            metadata={"kind": "event-trailer", "logical-identity": "3fa85f64-5717-4562-b3fc-2c963f66afa6"},
        ),
    )

    assert response.status_code == 404
