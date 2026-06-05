from contextlib import suppress
from typing import Any

from libs.redis_ext import redis_proxy
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.redis_cache.repositories import AdminEventCacheRepository
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.schemas.dtos import BaseEventDTO


async def update_event(session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
    dto = await AdminEventRepository.update(
        session=session,
        event_id=event_id,
        changes=changes,
    )

    with suppress(RedisError):
        await AdminEventCacheRepository.delete_by_id(redis=redis_proxy.redis, _id=event_id)

    return dto
