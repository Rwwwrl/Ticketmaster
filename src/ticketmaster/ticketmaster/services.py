from contextlib import suppress

from libs.aws.session import aws_session
from libs.redis_ext import redis_proxy
from redis.exceptions import RedisError
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.exceptions import EventCacheDocumentNotFoundException
from ticketmaster.redis_cache.repositories import EventCacheRepository
from ticketmaster.repositories import EventCursorDTO, EventRepository, TicketRepository, UserRepository
from ticketmaster.schemas.dtos import BaseEventDTO, BaseUserDTO


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
    async def get_event_by_id(cls, session: AsyncSession, _id: int) -> BaseEventDTO:
        with suppress(RedisError, EventCacheDocumentNotFoundException):
            return await EventCacheRepository.get_by_id(redis=redis_proxy.redis, _id=_id)

        event = await EventRepository.get_by_id(session=session, _id=_id)

        with suppress(RedisError):
            await EventCacheRepository.set(redis=redis_proxy.redis, dto=event)

        return event

    @classmethod
    async def list_events_page(
        cls,
        session: AsyncSession,
        cursor: EventCursorDTO | None,
        page_size: int,
    ) -> tuple[list[BaseEventDTO], EventCursorDTO | None]:
        event_ids, next_cursor = await EventRepository.list_ids_sorted_by_start_at(
            session=session,
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
