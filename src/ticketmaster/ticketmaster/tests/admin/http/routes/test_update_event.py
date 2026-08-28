from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from sqlmodel import select
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.models import Event
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import EventCacheRepository, NamespaceRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.settings import settings
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_update_event_when_single_field_returns_200_and_only_changes_that_field(
    async_client: AsyncClient, bypass_admin_jwt: None
) -> None:
    event = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
    )
    await insert(event)
    original_updated_at = event.updated_at

    response = await async_client.patch(url=f"/api/admin/events/{event.id}", json={"name": "Coldplay — Rescheduled"})

    assert response.status_code == 200
    body = EventResponseSchema(**response.json())
    assert body.name == "Coldplay — Rescheduled"
    assert body.description == "Stadium tour stop"
    assert body.type == EventTypeEnum.CONCERT
    assert body.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == event.id))).first()

        assert persisted.name == "Coldplay — Rescheduled"
        assert persisted.description == "Stadium tour stop"
        assert persisted.updated_at > original_updated_at


@pytest.mark.asyncio(loop_scope="session")
async def test_update_event_when_all_fields_returns_200_and_updates_all(
    async_client: AsyncClient, bypass_admin_jwt: None
) -> None:
    event = EventFactory(
        name="Lakers vs Celtics",
        description="NBA regular season game",
        type=EventTypeEnum.SPORT,
        start_at=datetime(2026, 5, 10, 19, 30, tzinfo=UTC),
    )
    await insert(event)

    payload = {
        "name": "Hamlet",
        "description": "Shakespeare in the park",
        "type": EventTypeEnum.THEATER,
        "start_at": datetime(2026, 7, 1, 18, 0, tzinfo=UTC).isoformat(),
    }

    response = await async_client.patch(url=f"/api/admin/events/{event.id}", json=payload)

    assert response.status_code == 200
    body = EventResponseSchema(**response.json())
    assert body.name == "Hamlet"
    assert body.description == "Shakespeare in the park"
    assert body.type == EventTypeEnum.THEATER
    assert body.start_at == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_event_when_cached_keeps_cache_entry_until_ttl(
    async_client: AsyncClient, redis: Redis, bypass_admin_jwt: None
) -> None:
    event = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
    )
    await insert(event)
    await EventCacheRepository.set(
        redis=redis,
        dto=BaseEventDTO.from_sqlmodel(model=event),
        version=settings.version,
    )
    key = EventCacheRepository._cache_key(event_id=event.id, version=settings.version)
    assert await redis.get(name=key) is not None

    response = await async_client.patch(url=f"/api/admin/events/{event.id}", json={"name": "Coldplay — Rescheduled"})
    raw = await redis.get(name=key)

    assert response.status_code == 200
    assert raw is not None
    cached_document = EventCacheDocument.from_raw_cache(raw)
    assert cached_document.name == "Coldplay"


@pytest.mark.asyncio(loop_scope="session")
async def test_update_event_when_not_found_returns_404(async_client: AsyncClient, bypass_admin_jwt: None) -> None:
    response = await async_client.patch(url="/api/admin/events/999999", json={"name": "Nope"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}


@pytest.mark.asyncio(loop_scope="session")
async def test_update_event_rotates_list_events_page_namespace(
    async_client: AsyncClient,
    redis: Redis,
    bypass_admin_jwt: None,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)
    previous_namespace = await NamespaceRepository.set(redis=redis)

    response = await async_client.patch(url=f"/api/admin/events/{event.id}", json={"name": "Updated"})
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 200
    assert current_namespace is not None
    assert current_namespace != previous_namespace
