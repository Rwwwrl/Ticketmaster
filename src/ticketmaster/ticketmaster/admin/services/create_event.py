from contextlib import suppress
from datetime import datetime
from decimal import Decimal

from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.redis_cache.utils import rotate_service_cache_namespace
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.enums import CurrencyEnum, EventTypeEnum
from ticketmaster.schemas.dtos import BaseEventDTO


async def create_event(
    session: AsyncSession,
    name: str,
    description: str,
    type: EventTypeEnum,
    start_at: datetime,
    price: Decimal,
    currency: CurrencyEnum,
) -> BaseEventDTO:
    dto = await AdminEventRepository.create(
        session=session,
        name=name,
        description=description,
        type=type,
        start_at=start_at,
        price=price,
        currency=currency,
    )

    # NOTE @sosov: Namespace rotation happens before the surrounding transaction commits. Moving
    # cache invalidation after commit is tracked separately.
    with suppress(RedisError):
        await rotate_service_cache_namespace()

    return dto
