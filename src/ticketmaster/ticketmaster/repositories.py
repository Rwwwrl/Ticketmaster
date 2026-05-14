from uuid import UUID

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.exceptions import UserNotFoundException
from ticketmaster.models import Event, User
from ticketmaster.schemas.dtos import BaseEventDTO, BaseUserDTO


class EventRepository:
    @classmethod
    async def get_all_paginated(
        cls,
        session: AsyncSession,
        page: int,
        page_size: int,
    ) -> tuple[list[BaseEventDTO], int]:
        """Return a slice of events for the requested page together with the total row count.

        Ordered by (start_at, id) ASC so pages are stable across requests.
        The total is returned alongside the items so the caller can expose page metadata
        without issuing a second query.
        """
        offset = (page - 1) * page_size
        items_result = await session.exec(
            select(Event).order_by(Event.start_at, Event.id).offset(offset).limit(page_size)
        )
        items = [BaseEventDTO.from_sqlmodel(model=event) for event in items_result.all()]

        total_result = await session.exec(select(func.count(Event.id)))
        total = total_result.one()

        return items, total


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
