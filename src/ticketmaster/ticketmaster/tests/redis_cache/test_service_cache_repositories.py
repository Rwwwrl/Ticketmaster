import json

import pytest
from libs.redis_ext.cache import FromRawCacheValidationError, ServiceCacheNotFoundException
from redis.asyncio import Redis
from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.redis_cache.repositories import ListEventsPageServiceCacheRepository, NamespaceRepository
from ticketmaster.redis_cache.service_caches import ListEventsPageServiceCache


@pytest.mark.asyncio(loop_scope="session")
async def test_namespace_repository_get_and_set(redis: Redis) -> None:
    assert NamespaceRepository._cache_key() == "namespace"

    namespace = await NamespaceRepository.set(redis=redis)

    assert await NamespaceRepository.get(redis=redis) == namespace
    assert await redis.ttl(NamespaceRepository._cache_key()) == -1


def test_list_events_page_service_cache_key_contains_complete_context() -> None:
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name="list_events_page",
        version="0.14.0",
        namespace="namespace-1",
        cursor="cursor-1",
        sort_key=EventSortKeyEnum.START_AT,
        page_size=50,
    )

    assert key == (
        "service=list_events_page:v=0.14.0:namespace=namespace-1:cursor=cursor-1:sort_key=start_at:page_size=50"
    )


def test_list_events_page_service_cache_key_isolates_version_and_namespace() -> None:
    common = {
        "service_name": "list_events_page",
        "cursor": "cursor-1",
        "sort_key": EventSortKeyEnum.START_AT,
        "page_size": 20,
    }

    first = ListEventsPageServiceCacheRepository.cache_key(version="0.13.0", namespace="namespace-1", **common)
    next_version = ListEventsPageServiceCacheRepository.cache_key(version="0.14.0", namespace="namespace-1", **common)
    next_namespace = ListEventsPageServiceCacheRepository.cache_key(version="0.13.0", namespace="namespace-2", **common)

    assert len({first, next_version, next_namespace}) == 3


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_service_cache_round_trip_and_ttl(redis: Redis) -> None:
    cache = ListEventsPageServiceCache(events_ids=[3, 1], next_cursor=None)
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name="list_events_page",
        version="0.14.0",
        namespace="namespace-1",
        cursor=None,
        sort_key=EventSortKeyEnum.PRICE,
        page_size=20,
    )

    await ListEventsPageServiceCacheRepository.set(
        redis=redis,
        key=key,
        value=cache,
        ttl_seconds=60,
    )

    restored = await ListEventsPageServiceCacheRepository.get(
        redis=redis,
        key=key,
    )

    assert restored == cache
    assert 0 < await redis.ttl(key) <= 60


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_service_cache_missing_value_raises(redis: Redis) -> None:
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name="list_events_page",
        version="0.14.0",
        namespace="namespace-1",
        cursor=None,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )

    with pytest.raises(ServiceCacheNotFoundException):
        await ListEventsPageServiceCacheRepository.get(
            redis=redis,
            key=key,
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_service_cache_malformed_value_raises(redis: Redis) -> None:
    key = ListEventsPageServiceCacheRepository.cache_key(
        service_name="list_events_page",
        version="0.14.0",
        namespace="namespace-1",
        cursor=None,
        sort_key=EventSortKeyEnum.START_AT,
        page_size=20,
    )
    await redis.set(name=key, value=json.dumps({"events_ids": "invalid", "next_cursor": None}))

    with pytest.raises(FromRawCacheValidationError):
        await ListEventsPageServiceCacheRepository.get(
            redis=redis,
            key=key,
        )
