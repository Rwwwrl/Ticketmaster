from contextlib import suppress

from libs.common.services import create_service_cursor, encode_service_cursor
from libs.redis_ext import redis_proxy
from libs.redis_ext.cache import FromRawCacheValidationError, ServiceCacheNotFoundException
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster import consts
from ticketmaster.cursors import EventCursorBodyDTO, EventCursorDTO, EventDBCursorDTO
from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.redis_cache.repositories import (
    EventCacheRepository,
    ListEventsPageServiceCacheRepository,
    NamespaceRepository,
)
from ticketmaster.redis_cache.service_caches import ListEventsPageServiceCache
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.settings import settings


async def _hydrate_events(session: AsyncSession, event_ids: list[int]) -> list[BaseEventDTO]:
    if not event_ids:
        return []

    cached_documents: list[BaseEventDTO] = []
    with suppress(RedisError):
        cached_documents = await EventCacheRepository.get_many_by_ids(
            redis=redis_proxy.redis,
            ids=event_ids,
            version=settings.version,
        )

    events_by_id: dict[int, BaseEventDTO] = {document.id: document for document in cached_documents}
    missing_ids: list[int] = [event_id for event_id in event_ids if event_id not in events_by_id]

    if missing_ids:
        events = await EventRepository.get_many_by_ids(session=session, ids=missing_ids)
        with suppress(RedisError):
            await EventCacheRepository.set_many(redis=redis_proxy.redis, dtos=events, version=settings.version)

        events_by_id.update({event.id: event for event in events})

    return [events_by_id[event_id] for event_id in event_ids if event_id in events_by_id]


async def list_events_page(
    session: AsyncSession,
    sort_key: EventSortKeyEnum,
    cursor: EventCursorDTO | None,
    page_size: int,
) -> tuple[list[BaseEventDTO], str | None]:
    if sort_key == EventSortKeyEnum.RANK:
        raise ValueError("sort_key=rank is not supported for list events")

    page_index = cursor.body.page_index if cursor is not None else 0
    service_name = list_events_page.__name__

    db_cursor = (
        EventDBCursorDTO(
            sort_key=cursor.body.sort_key,
            sort_key_value=cursor.body.sort_key_value,
            id=cursor.body.id,
        )
        if cursor is not None
        else None
    )

    namespace = None
    with suppress(RedisError):
        namespace = await NamespaceRepository.get(redis=redis_proxy.redis)

    fetched_namespace_successfully = namespace is not None
    should_page_be_in_cache = page_index <= consts.MAX_CACHED_PAGE_INDEX

    service_cache_key = (
        ListEventsPageServiceCacheRepository.cache_key(
            service_name=service_name,
            version=settings.version,
            namespace=namespace,
            cursor=encode_service_cursor(cursor=cursor) if cursor is not None else None,
            sort_key=sort_key,
            page_size=page_size,
        )
        if should_page_be_in_cache and fetched_namespace_successfully
        else None
    )

    if service_cache_key is not None:
        cached_page = None
        with suppress(RedisError, ServiceCacheNotFoundException, FromRawCacheValidationError):
            cached_page = await ListEventsPageServiceCacheRepository.get(
                redis=redis_proxy.redis,
                key=service_cache_key,
            )
        if cached_page is not None:
            items = await _hydrate_events(session=session, event_ids=cached_page.events_ids)
            return items, cached_page.next_cursor

    event_ids, next_cursor = await EventRepository.list_ids_paginated(
        session=session,
        sort_key=sort_key,
        cursor=db_cursor,
        page_size=page_size,
    )

    next_cursor: str = (
        encode_service_cursor(
            cursor=create_service_cursor(
                cursor_class=EventCursorDTO,
                body=EventCursorBodyDTO(
                    sort_key=next_cursor.sort_key,
                    sort_key_value=next_cursor.sort_key_value,
                    id=next_cursor.id,
                    page_index=page_index + 1,
                ),
                secret=settings.secret,
            ),
        )
        if next_cursor is not None
        else None
    )

    items = await _hydrate_events(session=session, event_ids=event_ids)

    if service_cache_key is not None:
        with suppress(RedisError):
            await ListEventsPageServiceCacheRepository.set(
                redis=redis_proxy.redis,
                key=service_cache_key,
                value=ListEventsPageServiceCache(events_ids=event_ids, next_cursor=next_cursor),
            )

    return items, next_cursor
