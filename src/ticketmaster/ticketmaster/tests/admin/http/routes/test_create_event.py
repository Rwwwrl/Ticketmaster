from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from redis.asyncio import Redis
from sqlmodel import select
from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.models import Event
from ticketmaster.redis_cache.repositories import NamespaceRepository


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_when_valid_payload_returns_201_and_persists(
    async_client: AsyncClient, bypass_admin_jwt: None
) -> None:
    payload = {
        "name": "Coldplay",
        "description": "Stadium tour stop",
        "type": EventTypeEnum.CONCERT,
        "start_at": datetime(2026, 6, 2, 20, 0, tzinfo=UTC).isoformat(),
        "price": "49.99",
        "currency": CurrencyEnum.EUR,
    }

    response = await async_client.post(url="/api/admin/events/", json=payload)

    assert response.status_code == 201
    body = EventResponseSchema(**response.json())
    assert body.id is not None
    assert body.name == payload["name"]
    assert body.description == payload["description"]
    assert body.type == EventTypeEnum.CONCERT
    assert body.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)
    assert body.price == Decimal("49.99")
    assert body.currency == CurrencyEnum.EUR

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == body.id))).first()

        assert persisted is not None
        assert persisted.name == payload["name"]
        assert persisted.description == payload["description"]
        assert persisted.type == EventTypeEnum.CONCERT
        assert persisted.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)
        assert persisted.price == Decimal("49.99")
        assert persisted.currency == CurrencyEnum.EUR


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_when_missing_field_returns_422(async_client: AsyncClient, bypass_admin_jwt: None) -> None:
    payload = {
        "name": "Coldplay",
        "type": EventTypeEnum.CONCERT,
        "start_at": datetime(2026, 6, 2, 20, 0, tzinfo=UTC).isoformat(),
    }

    response = await async_client.post(url="/api/admin/events/", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_rotates_list_events_page_namespace(
    async_client: AsyncClient,
    redis: Redis,
    bypass_admin_jwt: None,
) -> None:
    previous_namespace = await NamespaceRepository.set(redis=redis)
    payload = {
        "name": "Coldplay",
        "description": "Stadium tour stop",
        "type": EventTypeEnum.CONCERT,
        "start_at": datetime(2026, 6, 2, 20, 0, tzinfo=UTC).isoformat(),
        "price": "49.99",
        "currency": CurrencyEnum.EUR,
    }

    response = await async_client.post(url="/api/admin/events/", json=payload)
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 201
    assert current_namespace is not None
    assert current_namespace != previous_namespace
