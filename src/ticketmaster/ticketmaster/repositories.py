from datetime import datetime, timedelta
from uuid import UUID

from libs.datetime_ext.utils import utc_now
from sqlalchemy import and_, delete, func, or_, tuple_, update
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.cursors import EventDBCursorDTO
from ticketmaster.enums import EventSortKeyEnum, TicketStatusEnum
from ticketmaster.exceptions import EventNotFoundException, UserNotFoundException
from ticketmaster.models import Event, Ticket, User
from ticketmaster.schemas.dtos import BaseEventDTO, BaseTicketDTO, BaseUserDTO

_SORT_KEY_TO_POSTGRES_COLUMN: dict[EventSortKeyEnum, InstrumentedAttribute] = {
    EventSortKeyEnum.START_AT: Event.start_at,
    EventSortKeyEnum.PRICE: Event.price,
}


class EventRepository:
    @classmethod
    async def get_by_id(cls, session: AsyncSession, _id: int) -> BaseEventDTO:
        result = await session.exec(select(Event).where(Event.id == _id))
        event = result.first()

        if event is None:
            raise EventNotFoundException(f"Event not found for id={_id}")

        return BaseEventDTO.from_sqlmodel(model=event)

    @classmethod
    async def list_ids_paginated(
        cls,
        session: AsyncSession,
        sort_key: EventSortKeyEnum,
        cursor: EventDBCursorDTO | None,
        page_size: int,
    ) -> tuple[list[int], EventDBCursorDTO | None]:
        effective_sort_key = cursor.sort_key if cursor is not None else sort_key
        column = _SORT_KEY_TO_POSTGRES_COLUMN[effective_sort_key]

        statement = select(Event.id, column).order_by(column, Event.id).limit(page_size + 1)

        if cursor is not None:
            statement = statement.where(tuple_(column, Event.id) > tuple_(cursor.sort_key_value, cursor.id))

        rows = (await session.exec(statement)).all()
        has_next_page = len(rows) > page_size
        kept_rows = rows[:page_size]

        ids = [event_id for event_id, _value in kept_rows]

        if has_next_page:
            last_event_id, last_column_value = kept_rows[-1]
            next_cursor = EventDBCursorDTO(
                sort_key=effective_sort_key,
                sort_key_value=last_column_value,
                id=last_event_id,
            )
        else:
            next_cursor = None

        return ids, next_cursor

    @classmethod
    async def get_many_by_ids(cls, session: AsyncSession, ids: list[int]) -> list[BaseEventDTO]:
        if not ids:
            return []

        rows = (await session.exec(select(Event).where(Event.id.in_(ids)))).all()
        return [BaseEventDTO.from_sqlmodel(model=event) for event in rows]

    @classmethod
    async def search_after_cursor(
        cls,
        session: AsyncSession,
        q: str,
        cursor: EventDBCursorDTO | None,
        page_size: int,
    ) -> tuple[list[BaseEventDTO], EventDBCursorDTO | None]:
        tsquery = func.websearch_to_tsquery("english", q)
        rank_expr = func.ts_rank(Event.search_vector, tsquery)

        statement = (
            select(Event, rank_expr.label("rank"))
            .where(Event.search_vector.op("@@")(tsquery))
            .order_by(rank_expr.desc(), Event.id.asc())
            .limit(page_size + 1)
        )
        if cursor is not None:
            statement = statement.where(
                or_(
                    rank_expr < cursor.sort_key_value,
                    and_(rank_expr == cursor.sort_key_value, Event.id > cursor.id),
                )
            )

        rows = (await session.exec(statement)).all()
        has_next_page = len(rows) > page_size
        kept_rows = rows[:page_size]
        items = [BaseEventDTO.from_sqlmodel(model=event) for event, _rank in kept_rows]
        if has_next_page:
            last_event, last_rank = kept_rows[-1]
            next_cursor = EventDBCursorDTO(
                sort_key=EventSortKeyEnum.RANK,
                sort_key_value=last_rank,
                id=last_event.id,
            )
        else:
            next_cursor = None
        return items, next_cursor


class TicketRepository:
    @classmethod
    async def get_by_id(cls, session: AsyncSession, ticket_id: int) -> BaseTicketDTO:
        result = await session.exec(select(Ticket).where(Ticket.id == ticket_id))
        return BaseTicketDTO.from_sqlmodel(model=result.one())

    @classmethod
    async def get_all_by_event_id(cls, session: AsyncSession, event_id: int) -> list[BaseTicketDTO]:
        result = await session.exec(select(Ticket).where(Ticket.event_id == event_id).order_by(Ticket.id))
        return [BaseTicketDTO.from_sqlmodel(model=ticket) for ticket in result.all()]

    @classmethod
    async def reserve(
        cls,
        session: AsyncSession,
        event_id: int,
        ticket_id: int,
        user_id: int,
        now: datetime,
        reservation_ttl: timedelta,
    ) -> bool:
        """Conditionally claim a ticket for ``user_id``; returns ``True`` iff the row was updated.

        The single UPDATE flips status to RESERVED only when the ticket is AVAILABLE or
        held by a stale reservation older than ``reservation_ttl`` — that conditional WHERE
        is what prevents two concurrent callers from reserving the same ticket.
        """
        stmt = (
            update(Ticket)
            .where(
                Ticket.id == ticket_id,
                Ticket.event_id == event_id,
                or_(
                    Ticket.status == TicketStatusEnum.AVAILABLE,
                    and_(
                        Ticket.status == TicketStatusEnum.RESERVED,
                        Ticket.reserved_at < now - reservation_ttl,
                    ),
                ),
            )
            .values(
                status=TicketStatusEnum.RESERVED,
                reserved_at=now,
                user_id=user_id,
                updated_at=utc_now(),
            )
        )
        result = await session.exec(stmt)
        return result.rowcount == 1

    @classmethod
    async def book(
        cls,
        session: AsyncSession,
        event_id: int,
        ticket_id: int,
        user_id: int,
        now: datetime,
        reservation_ttl: timedelta,
    ) -> bool:
        """Confirm a fresh reservation held by ``user_id``; returns ``True`` iff the row was updated.

        The conditional WHERE flips RESERVED→BOOKED only when the same user still holds a
        reservation that has not lapsed, so a stale or third-party reservation cannot be booked.
        """
        stmt = (
            update(Ticket)
            .where(
                Ticket.id == ticket_id,
                Ticket.event_id == event_id,
                Ticket.user_id == user_id,
                Ticket.status == TicketStatusEnum.RESERVED,
                Ticket.reserved_at > now - reservation_ttl,
            )
            .values(
                status=TicketStatusEnum.BOOKED,
                booked_at=now,
                updated_at=utc_now(),
            )
        )
        result = await session.exec(stmt)
        return result.rowcount == 1

    @classmethod
    async def release_reserved_for_user(cls, session: AsyncSession, user_id: int) -> None:
        stmt = (
            update(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status == TicketStatusEnum.RESERVED)
            .values(
                status=TicketStatusEnum.AVAILABLE,
                user_id=None,
                reserved_at=None,
                updated_at=utc_now(),
            )
        )
        await session.exec(stmt)

    @classmethod
    async def anonymize_booked_for_user(cls, session: AsyncSession, user_id: int) -> None:
        stmt = (
            update(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status == TicketStatusEnum.BOOKED)
            .values(
                status=TicketStatusEnum.ANONYMOUS_BOOKED,
                user_id=None,
                updated_at=utc_now(),
            )
        )
        await session.exec(stmt)


class UserRepository:
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        uuid: UUID,
        pool_id: str,
        email: str,
        cognito_username: str,
    ) -> BaseUserDTO:
        user = User(uuid=uuid, pool_id=pool_id, email=email, cognito_username=cognito_username)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return BaseUserDTO.from_sqlmodel(model=user)

    @classmethod
    async def get_by_pool_and_cognito_username(
        cls,
        session: AsyncSession,
        pool_id: str,
        cognito_username: str,
    ) -> BaseUserDTO:
        user = await session.scalar(
            select(User).where(User.pool_id == pool_id, User.cognito_username == cognito_username)
        )

        if user is None:
            raise UserNotFoundException(f"User not found for pool_id={pool_id} cognito_username={cognito_username}")

        return BaseUserDTO.from_sqlmodel(model=user)

    @classmethod
    async def delete_by_id(cls, session: AsyncSession, user_id: int) -> None:
        await session.exec(delete(User).where(User.id == user_id))
