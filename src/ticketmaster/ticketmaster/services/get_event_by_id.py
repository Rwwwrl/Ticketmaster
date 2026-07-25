from contextlib import suppress

from libs.redis_ext import redis_proxy
from libs.redis_ext.cache import FromRawCacheValidationError
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.exceptions import EventCacheDocumentNotFoundException
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.settings import settings


async def get_event_by_id(session: AsyncSession, _id: int) -> BaseEventDTO:
    with suppress(RedisError, EventCacheDocumentNotFoundException, FromRawCacheValidationError):
        return await EventCacheRepository.get_by_id(redis=redis_proxy.redis, _id=_id, version=settings.version)

    event = await EventRepository.get_by_id(session=session, _id=_id)

    with suppress(RedisError):
        await EventCacheRepository.set(redis=redis_proxy.redis, dto=event, version=settings.version)

    return event
