from datetime import UTC, datetime

import pytest
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from ticketmaster.admin.services.invalidate_event_cache_document_by_id import invalidate_event_cache_document_by_id
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_invalidate_event_cache_document_by_id_deletes_adjacent_version_keys(redis: Redis) -> None:
    event = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    await insert(event)

    cache_document = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=event))
    current_version = EventCacheDocument.version
    adjacent_versions = (current_version - 1, current_version, current_version + 1)
    for version in adjacent_versions:
        key = EventCacheRepository._event_key_for_version(event_id=event.id, version=version)
        await redis.set(name=key, value=cache_document.model_dump_json())

    await invalidate_event_cache_document_by_id(_id=event.id)

    for version in adjacent_versions:
        key = EventCacheRepository._event_key_for_version(event_id=event.id, version=version)
        assert await redis.get(name=key) is None


@pytest.mark.asyncio(loop_scope="session")
async def test_invalidate_event_cache_document_by_id_keeps_other_event_keys(redis: Redis) -> None:
    invalidated = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    untouched = EventFactory(start_at=datetime(2026, 5, 2, tzinfo=UTC))
    await insert(invalidated, untouched)

    untouched_document = EventCacheDocument.from_dto(dto=BaseEventDTO.from_sqlmodel(model=untouched))
    untouched_key = EventCacheRepository._event_key_for_version(
        event_id=untouched.id, version=EventCacheDocument.version
    )
    await redis.set(name=untouched_key, value=untouched_document.model_dump_json())

    await invalidate_event_cache_document_by_id(_id=invalidated.id)

    assert await redis.get(name=untouched_key) is not None
