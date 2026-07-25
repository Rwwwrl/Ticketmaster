import json
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import update
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.models import Event
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.settings import settings
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_warms_cache_on_first_request(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
    )
    await insert(event)

    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 0

    response = await async_client.get(url=f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert EventResponseSchema(**response.json()).name == "Coldplay"
    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_serves_from_cache_when_db_row_changes_underneath(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(
        name="Original Name",
        description="Original description",
        type=EventTypeEnum.SPORT,
        start_at=datetime(2026, 5, 10, 19, 30, tzinfo=UTC),
    )
    await insert(event)

    warmup_response = await async_client.get(url=f"/v1/events/{event.id}")
    assert warmup_response.status_code == 200

    async with Session() as session, session.begin():
        await session.exec(update(Event).where(Event.id == event.id).values(name="Modified Name"))

    second_response = await async_client.get(url=f"/v1/events/{event.id}")

    assert second_response.status_code == 200
    assert EventResponseSchema(**second_response.json()).name == "Original Name"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_falls_through_to_db_when_cache_document_is_stale(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(
        name="Stale Cache Show",
        start_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    await insert(event)

    stale_payload = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=event)).model_dump(
        mode="json", exclude={"price"}
    )
    await redis.set(
        name=EventCacheRepository._cache_key(event_id=event.id, version=settings.version),
        value=json.dumps(stale_payload),
    )

    response = await async_client.get(url=f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert EventResponseSchema(**response.json()).name == "Stale Cache Show"

    rewarmed_document = EventCacheDocument.from_raw_cache(
        await redis.get(name=EventCacheRepository._cache_key(event_id=event.id, version=settings.version))
    )
    assert rewarmed_document.id == event.id


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_falls_through_to_db_when_redis_errors(
    async_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = EventFactory(
        name="Resilient Show",
        start_at=datetime(2026, 5, 1, tzinfo=UTC),
    )
    await insert(event)

    async def _failing_get(*args, **kwargs) -> None:
        raise RedisError("get boom")

    async def _failing_set(*args, **kwargs) -> None:
        raise RedisError("set boom")

    monkeypatch.setattr(redis, "get", _failing_get)
    monkeypatch.setattr(redis, "set", _failing_set)

    response = await async_client.get(url=f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert EventResponseSchema(**response.json()).id == event.id
