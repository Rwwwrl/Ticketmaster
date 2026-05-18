import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Self
from uuid import UUID

from libs.common.schemas.dto import DTO
from libs.datetime_ext.utils import utc_now
from sqlalchemy import and_, or_, tuple_, update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.enums import TicketStatusEnum
from ticketmaster.exceptions import UserNotFoundException
from ticketmaster.models import Event, Ticket, User
from ticketmaster.schemas.dtos import BaseEventDTO, BaseTicketDTO, BaseUserDTO


class EventCursorDTO(DTO):
    started_at: datetime
    id: int

    def encode(self) -> str:
        raw = json.dumps(obj={"started_at": self.started_at.isoformat(), "_id": self.id}).encode()
        return base64.urlsafe_b64encode(s=raw).decode()

    @classmethod
    def decode(cls, cursor: str) -> Self:
        try:
            raw = base64.b64decode(s=cursor.encode(), altchars=b"-_", validate=True)
            payload = json.loads(raw)
            return cls(started_at=datetime.fromisoformat(payload["started_at"]), id=int(payload["_id"]))
        except binascii.Error, KeyError, TypeError, ValueError:
            raise ValueError("Invalid event cursor")


class EventRepository:
    @classmethod
    async def list_after_cursor(
        cls,
        session: AsyncSession,
        cursor: EventCursorDTO | None,
        page_size: int,
    ) -> tuple[list[BaseEventDTO], EventCursorDTO | None]:
        statement = select(Event).order_by(Event.start_at, Event.id).limit(page_size + 1)
        if cursor is not None:
            statement = statement.where(tuple_(Event.start_at, Event.id) > tuple_(cursor.started_at, cursor.id))

        items_result = await session.exec(statement)
        rows = items_result.all()
        has_next_page = len(rows) > page_size
        kept_rows = rows[:page_size]
        items = [BaseEventDTO.from_sqlmodel(model=event) for event in kept_rows]
        next_cursor = EventCursorDTO(started_at=items[-1].start_at, id=items[-1].id) if has_next_page else None

        return items, next_cursor


class TicketRepository:
    @classmethod
    async def get_by_id(cls, session: AsyncSession, ticket_id: int) -> BaseTicketDTO:
        result = await session.exec(select(Ticket).where(Ticket.id == ticket_id))
        return BaseTicketDTO.from_sqlmodel(model=result.one())

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


class UserRepository:
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        uuid: UUID,
        pool_id: str,
        email: str,
        external_id: str,
    ) -> BaseUserDTO:
        user = User(uuid=uuid, pool_id=pool_id, email=email, external_id=external_id)
        session.add(user)
        await session.flush()
        await session.refresh(user)
        return BaseUserDTO.from_sqlmodel(model=user)

    @classmethod
    async def get_by_pool_and_external_id(
        cls,
        session: AsyncSession,
        pool_id: str,
        external_id: str,
    ) -> BaseUserDTO:
        user = await session.scalar(select(User).where(User.pool_id == pool_id, User.external_id == external_id))

        if user is None:
            raise UserNotFoundException(f"User not found for pool_id={pool_id} external_id={external_id}")

        return BaseUserDTO.from_sqlmodel(model=user)
