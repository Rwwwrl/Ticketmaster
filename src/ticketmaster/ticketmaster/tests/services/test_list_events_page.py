import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from libs.common.services import create_service_cursor, decode_service_cursor, encode_service_cursor
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import update
from ticketmaster.cursors import EventCursorBodyDTO, EventCursorDTO
from ticketmaster.enums import EventSortKeyEnum, EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventsPageResponseSchema
from ticketmaster.models import Event
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import (
    EventCacheRepository,
    ListEventsPageServiceCacheRepository,
    NamespaceRepository,
)
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.services.list_events_page import list_events_page
from ticketmaster.settings import settings
from ticketmaster.tests.factories import EventFactory


@pytest_asyncio.fixture(autouse=True)
async def _namespace(redis: Redis) -> None:
    await NamespaceRepository.set(redis=redis)


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

    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 0

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})

    assert response.status_code == 200
    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 1


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
    await redis.set(
        name=EventCacheRepository._cache_key(event_id=first.id, version=settings.version),
        value=cache_document.model_dump_json(),
    )
    assert await redis.exists(EventCacheRepository._cache_key(event_id=second.id, version=settings.version)) == 0

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [first.id, second.id]
    assert await redis.exists(EventCacheRepository._cache_key(event_id=second.id, version=settings.version)) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_backfills_when_cache_document_is_stale(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)

    stale_payload = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=event)).model_dump(
        mode="json", exclude={"price"}
    )
    await redis.set(
        name=EventCacheRepository._cache_key(event_id=event.id, version=settings.version),
        value=json.dumps(stale_payload),
    )

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [event.id]

    rewarmed_document = EventCacheDocument.from_raw_cache(
        await redis.get(name=EventCacheRepository._cache_key(event_id=event.id, version=settings.version))
    )
    assert rewarmed_document.id == event.id


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_ignores_other_version_cache_keys(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)

    cache_document = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=event))
    other_version_key = EventCacheRepository._cache_key(event_id=event.id, version="other-version")
    await redis.set(name=other_version_key, value=cache_document.model_dump_json())
    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 0

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [event.id]
    assert await redis.exists(EventCacheRepository._cache_key(event_id=event.id, version=settings.version)) == 1
    assert await redis.exists(other_version_key) == 1


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

    async def _failing_get(*args, **kwargs) -> None:
        raise RedisError("get boom")

    def _failing_pipeline(*args, **kwargs) -> None:
        raise RedisError("pipeline boom")

    monkeypatch.setattr(redis, "get", _failing_get)
    monkeypatch.setattr(redis, "mget", _failing_mget)
    monkeypatch.setattr(redis, "pipeline", _failing_pipeline)

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    page = EventsPageResponseSchema(**response.json())

    assert response.status_code == 200
    assert [item.id for item in page.items] == [event.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_warms_and_reuses_page_cache(
    async_client: AsyncClient,
    redis: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)
    namespace = await NamespaceRepository.set(redis=redis)

    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name=list_events_page.__name__,
        version=settings.version,
        namespace=namespace,
        cursor=None,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )
    assert first_response.status_code == 200
    assert await redis.exists(key) == 1

    async def _unexpected_database_query(*args, **kwargs) -> None:
        raise AssertionError("page cache hit queried PostgreSQL for event IDs")

    monkeypatch.setattr(EventRepository, "list_ids_paginated", _unexpected_database_query)

    second_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})

    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_recomputes_page_with_malformed_service_cache(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)
    namespace = await NamespaceRepository.get(redis=redis)
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name=list_events_page.__name__,
        version=settings.version,
        namespace=namespace,
        cursor=None,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )
    await redis.set(name=key, value=json.dumps({"events_ids": "invalid", "next_cursor": None}))

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    restored = await ListEventsPageServiceCacheRepository.get(
        redis=redis,
        key=key,
    )

    assert response.status_code == 200
    assert restored.events_ids == [event.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_old_cursor_populates_current_namespace(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    events = [EventFactory(start_at=datetime(2026, 5, day, tzinfo=UTC)) for day in range(1, 22)]
    await insert(*events)
    old_namespace = await NamespaceRepository.set(redis=redis)
    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    first_page = EventsPageResponseSchema(**first_response.json())
    assert first_page.next_cursor is not None

    current_namespace = await NamespaceRepository.set(redis=redis)
    second_response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "start_at", "cursor": first_page.next_cursor},
    )
    current_key = ListEventsPageServiceCacheRepository.cache_key(
        service_name=list_events_page.__name__,
        version=settings.version,
        namespace=current_namespace,
        cursor=first_page.next_cursor,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )
    old_key = ListEventsPageServiceCacheRepository.cache_key(
        service_name=list_events_page.__name__,
        version=settings.version,
        namespace=old_namespace,
        cursor=first_page.next_cursor,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )

    assert second_response.status_code == 200
    assert await redis.exists(current_key) == 1
    assert await redis.exists(old_key) == 0


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(("page_index", "expected_cached"), [(4, True), (5, False)])
async def test_list_events_page_caches_only_first_five_pages(
    async_client: AsyncClient,
    redis: Redis,
    page_index: int,
    expected_cached: bool,
) -> None:
    events = [EventFactory(start_at=datetime(2026, 5, 1, hour=index, tzinfo=UTC)) for index in range(21)]
    await insert(*events)
    namespace = await NamespaceRepository.set(redis=redis)
    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    first_page = EventsPageResponseSchema(**first_response.json())
    assert first_page.next_cursor is not None

    decoded = decode_service_cursor(
        encoded_cursor=first_page.next_cursor,
        cursor_class=EventCursorDTO,
        secret=settings.secret,
    )
    cursor = encode_service_cursor(
        cursor=create_service_cursor(
            cursor_class=EventCursorDTO,
            body=EventCursorBodyDTO(
                sort_key=decoded.body.sort_key,
                sort_key_value=decoded.body.sort_key_value,
                id=decoded.body.id,
                page_index=page_index,
            ),
            secret=settings.secret,
        ),
    )
    response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "start_at", "cursor": cursor},
    )
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name=list_events_page.__name__,
        version=settings.version,
        namespace=namespace,
        cursor=cursor,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )

    assert response.status_code == 200
    assert bool(await redis.exists(key)) is expected_cached
