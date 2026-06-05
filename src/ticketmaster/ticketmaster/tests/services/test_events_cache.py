from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import update
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema, EventsPageResponseSchema
from ticketmaster.models import Event
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_warms_cache_on_first_request(
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

    assert await redis.exists(EventCacheRepository._event_key(event_id=event.id)) == 0

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})

    assert response.status_code == 200
    assert await redis.exists(EventCacheRepository._event_key(event_id=event.id)) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_serves_from_cache_when_db_row_changes_underneath(
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

    warmup_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    assert warmup_response.status_code == 200

    async with Session() as session, session.begin():
        await session.exec(update(Event).where(Event.id == event.id).values(name="Modified Name"))

    second_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    second_page = EventsPageResponseSchema(**second_response.json())

    assert second_response.status_code == 200
    assert second_page.items[0].name == "Original Name"


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_backfills_on_partial_cache_miss(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    first = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    second = EventFactory(start_at=datetime(2026, 5, 2, tzinfo=UTC))
    await insert(first, second)

    cache_document = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=first))
    await redis.set(name=EventCacheRepository._event_key(event_id=first.id), value=cache_document.model_dump_json())
    assert await redis.exists(EventCacheRepository._event_key(event_id=second.id)) == 0

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [first.id, second.id]
    assert await redis.exists(EventCacheRepository._event_key(event_id=second.id)) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_falls_through_to_db_when_redis_errors(
    async_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)

    async def _failing_mget(*args, **kwargs) -> None:
        raise RedisError("mget boom")

    def _failing_pipeline(*args, **kwargs) -> None:
        raise RedisError("pipeline boom")

    monkeypatch.setattr(redis, "mget", _failing_mget)
    monkeypatch.setattr(redis, "pipeline", _failing_pipeline)

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [event.id]


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

    assert await redis.exists(EventCacheRepository._event_key(event_id=event.id)) == 0

    response = await async_client.get(url=f"/v1/events/{event.id}")

    assert response.status_code == 200
    assert EventResponseSchema(**response.json()).name == "Coldplay"
    assert await redis.exists(EventCacheRepository._event_key(event_id=event.id)) == 1


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
