from contextlib import suppress

from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.exceptions import EventHasTicketsException
from ticketmaster.admin.redis_cache.utils import rotate_service_redis_cache_namespace
from ticketmaster.admin.repositories import AdminEventRepository, AdminTicketRepository


async def delete_event(session: AsyncSession, event_id: int) -> None:
    event = await AdminEventRepository.get_for_update(session=session, _id=event_id)

    if await AdminTicketRepository.exists(session=session, event_id=event.id):
        raise EventHasTicketsException(f"Event has tickets for id={event_id}")

    await AdminEventRepository.delete(session=session, _id=event.id)

    # NOTE @sosov: Namespace rotation happens before the surrounding transaction commits. Moving
    # cache invalidation after commit is tracked separately.
    with suppress(RedisError):
        await rotate_service_redis_cache_namespace()
