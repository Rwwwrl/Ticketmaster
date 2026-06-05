from contextlib import suppress
from datetime import datetime
from decimal import Decimal
from typing import Any

from libs.redis_ext import redis_proxy
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.redis_cache.repositories import AdminEventCacheRepository
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.services import EventService


class AdminEventService(EventService):
    @classmethod
    async def create_event(
        cls,
        session: AsyncSession,
        name: str,
        description: str,
        type: EventTypeEnum,
        start_at: datetime,
        price: Decimal,
        currency: CurrencyEnum,
    ) -> BaseEventDTO:
        return await AdminEventRepository.create(
            session=session,
            name=name,
            description=description,
            type=type,
            start_at=start_at,
            price=price,
            currency=currency,
        )

    @classmethod
    async def update_event(cls, session: AsyncSession, event_id: int, changes: dict[str, Any]) -> BaseEventDTO:
        dto = await AdminEventRepository.update(
            session=session,
            event_id=event_id,
            changes=changes,
        )

        with suppress(RedisError):
            await AdminEventCacheRepository.delete_by_id(redis=redis_proxy.redis, _id=event_id)

        return dto
