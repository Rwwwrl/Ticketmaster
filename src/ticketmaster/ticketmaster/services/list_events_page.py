from contextlib import suppress

from libs.redis_ext import redis_proxy
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.cursors import EventCursorDTO
from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.exceptions import CursorSortKeyMismatchException
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO


async def list_events_page(
    session: AsyncSession,
    sort_key: EventSortKeyEnum,
    cursor: EventCursorDTO | None,
    page_size: int,
) -> tuple[list[BaseEventDTO], EventCursorDTO | None]:
    if cursor is not None and cursor.sort_key != sort_key:
        raise CursorSortKeyMismatchException("`cursor.sort_key` and `sort_key` mismatch")

    event_ids, next_cursor = await EventRepository.list_ids_paginated(
        session=session,
        sort_key=sort_key,
        cursor=cursor,
        page_size=page_size,
    )

    if not event_ids:
        return [], next_cursor

    cached_documents: list[BaseEventDTO] = []
    with suppress(RedisError):
        cached_documents = await EventCacheRepository.get_many_by_ids(redis=redis_proxy.redis, ids=event_ids)

    events_by_id: dict[int, BaseEventDTO] = {
        cached_document.id: cached_document for cached_document in cached_documents
    }

    missing_in_cache_ids: list[int] = [event_id for event_id in event_ids if event_id not in events_by_id]

    if missing_in_cache_ids:
        events = await EventRepository.get_many_by_ids(session=session, ids=missing_in_cache_ids)

        with suppress(RedisError):
            await EventCacheRepository.set_many(redis=redis_proxy.redis, dtos=events)

        for event in events:
            events_by_id[event.id] = event

    ordered_items = [events_by_id[event_id] for event_id in event_ids]

    return ordered_items, next_cursor
