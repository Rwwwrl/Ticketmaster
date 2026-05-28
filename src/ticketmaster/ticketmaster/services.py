import logging

from libs.aws.session import aws_session
from libs.redis_ext import redis_proxy
from libs.sqlmodel_ext import Session
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.repositories import EventCursorDTO, EventRepository, TicketRepository, UserRepository
from ticketmaster.schemas.dtos import BaseEventDTO, BaseUserDTO

_logger = logging.getLogger(__name__)


class UserService:
    @classmethod
    async def delete_user(cls, session: AsyncSession, user: BaseUserDTO) -> None:
        await TicketRepository.release_reserved_for_user(session=session, user_id=user.id)
        await TicketRepository.anonymize_booked_for_user(session=session, user_id=user.id)
        await UserRepository.delete_by_id(session=session, user_id=user.id)

        async with aws_session.client(service_name="cognito-idp") as cognito:
            try:
                await cognito.admin_delete_user(UserPoolId=user.pool_id, Username=user.cognito_username)
            except cognito.exceptions.UserNotFoundException:
                pass


class EventService:
    @classmethod
    async def list_events_page(
        cls,
        cursor: EventCursorDTO | None,
        page_size: int,
    ) -> tuple[list[BaseEventDTO], EventCursorDTO | None]:
        async with Session() as session, session.begin():
            event_ids, next_cursor = await EventRepository.list_ids_sorted_by_start_at(
                session=session,
                cursor=cursor,
                page_size=page_size,
            )

            if not event_ids:
                return [], next_cursor

            try:
                cached_documents = await EventCacheRepository.get_many_by_ids(redis=redis_proxy.redis, ids=event_ids)
            except RedisError:
                _logger.warning("event cache read failed; falling through to DB", exc_info=True)
                cached_documents = []

            events_by_id: dict[int, BaseEventDTO] = {
                cached_document.id: cached_document for cached_document in cached_documents
            }

            missing_in_cache_ids: list[int] = [event_id for event_id in event_ids if event_id not in events_by_id]

            if missing_in_cache_ids:
                events = await EventRepository.get_many_by_ids(session=session, ids=missing_in_cache_ids)

                try:
                    await EventCacheRepository.set_many(redis=redis_proxy.redis, dtos=events)
                except RedisError:
                    _logger.warning("event cache write failed; cache backfill skipped", exc_info=True)

                for event in events:
                    events_by_id[event.id] = event

            ordered_items = [events_by_id[event_id] for event_id in event_ids]

            return ordered_items, next_cursor
