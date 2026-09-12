from collections.abc import Awaitable, Callable
from contextlib import suppress

from libs.common.schemas.dto import DTO
from pydantic import ValidationError
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.admin.enums import S3EventKindEnum
from ticketmaster.admin.exceptions import UnsupportedS3ObjectException
from ticketmaster.admin.redis_cache.utils import rotate_service_redis_cache_namespace
from ticketmaster.admin.repositories import AdminEventRepository
from ticketmaster.admin.schemas.dtos import EventTrailerCreatedDTO
from ticketmaster.repositories import EventRepository


async def _handle_event_trailer(session: AsyncSession, event: EventTrailerCreatedDTO) -> None:
    matched_event = await EventRepository.get_by_logical_identity(
        session=session,
        logical_identity=event.meta.logical_identity,
    )

    await AdminEventRepository.update(
        session=session,
        _id=matched_event.id,
        changes={"trailer_bucket": event.bucket, "trailer_key": event.key},
    )

    # NOTE @sosov: Namespace rotation happens before the surrounding transaction commits. Moving
    # cache invalidation after commit is tracked separately (same tradeoff as update_event).
    with suppress(RedisError):
        await rotate_service_redis_cache_namespace()


_HANDLERS: dict[str, tuple[type[DTO], Callable[..., Awaitable[None]]]] = {
    S3EventKindEnum.EVENT_TRAILER: (EventTrailerCreatedDTO, _handle_event_trailer),
}


async def process_s3_event(session: AsyncSession, bucket: str, key: str, metadata: dict[str, str]) -> None:
    kind = metadata.get("kind")
    entry = _HANDLERS.get(kind) if kind is not None else None

    # NOTE @sosov: An s3 object kind we don't have a handler for (yet, or ever) is not an
    # error — succeed silently so the lambda never retries and the event is simply ignored.
    if entry is None:
        return

    event_cls, handler = entry

    try:
        event = event_cls.model_validate({"bucket": bucket, "key": key, "meta": metadata})
    except ValidationError:
        raise UnsupportedS3ObjectException(f"Invalid metadata for kind={kind} key={key}") from None

    await handler(session=session, event=event)
