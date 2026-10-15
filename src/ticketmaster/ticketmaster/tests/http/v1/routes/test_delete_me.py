"""Endpoint contract tests for DELETE /api/v1/me/. Auth dependency is bypassed via dependency_overrides;
Cognito deletion is handed to the outbox, so no Cognito call is made by the route."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from libs.fastapi_ext.consts import REQUEST_ID_HEADER
from libs.sqlmodel_ext import SessionPrimary
from sqlmodel import select
from ticketmaster.enums import TicketStatusEnum
from ticketmaster.http.v1.dependencies import validate_user_jwt
from ticketmaster.models import OutboxMessage, Ticket, User
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.schemas.task_messages import DeleteCognitoUserTaskMessage
from ticketmaster.tests.factories import EventFactory, TicketFactory, UserFactory


@pytest_asyncio.fixture
async def signed_in_user_in_db(fastapi_app: FastAPI) -> AsyncIterator[BaseUserDTO]:
    async with SessionPrimary() as session, session.begin():
        user = UserFactory.build()
        session.add(user)
        await session.flush()
        await session.refresh(user)
        dto = BaseUserDTO.from_sqlmodel(model=user)

    fastapi_app.dependency_overrides[validate_user_jwt] = lambda: dto
    yield dto
    fastapi_app.dependency_overrides.clear()


async def _seed_ticket(*, user_id: int, status_: TicketStatusEnum) -> int:
    async with SessionPrimary() as session, session.begin():
        event = EventFactory.build()
        session.add(event)
        await session.flush()
        await session.refresh(event)

        ticket = TicketFactory.build(
            event_id=event.id,
            user_id=user_id,
            status=status_,
            reserved_at=datetime(2026, 5, 22, tzinfo=timezone.utc) if status_ == TicketStatusEnum.RESERVED else None,
            booked_at=datetime(2026, 5, 22, tzinfo=timezone.utc) if status_ == TicketStatusEnum.BOOKED else None,
        )
        session.add(ticket)
        await session.flush()
        await session.refresh(ticket)
        return ticket.id


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_no_tickets_returns_204_and_deletes_user(
    async_client: AsyncClient,
    signed_in_user_in_db: BaseUserDTO,
    mock_cognito: AsyncMock,
) -> None:
    response = await async_client.delete(url="/api/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    mock_cognito.admin_delete_user.assert_not_awaited()

    async with SessionPrimary() as session, session.begin():
        result = await session.exec(select(User).where(User.id == signed_in_user_in_db.id))
        assert result.first() is None
        [outbox_message] = (await session.exec(select(OutboxMessage))).all()
        session.expunge_all()

    assert outbox_message.code == DeleteCognitoUserTaskMessage.code
    delete_message = DeleteCognitoUserTaskMessage.model_validate(outbox_message.message)
    assert str(delete_message.logical_id) == response.headers[REQUEST_ID_HEADER]
    assert delete_message.pool_id == signed_in_user_in_db.pool_id
    assert delete_message.cognito_username == signed_in_user_in_db.cognito_username


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_user_has_reserved_tickets_releases_them(
    async_client: AsyncClient,
    signed_in_user_in_db: BaseUserDTO,
) -> None:
    ticket_id = await _seed_ticket(user_id=signed_in_user_in_db.id, status_=TicketStatusEnum.RESERVED)

    response = await async_client.delete(url="/api/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    async with SessionPrimary() as session, session.begin():
        ticket = (await session.exec(select(Ticket).where(Ticket.id == ticket_id))).one()
        assert ticket.status == TicketStatusEnum.AVAILABLE
        assert ticket.user_id is None
        assert ticket.reserved_at is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_user_has_booked_tickets_marks_anonymous_booked(
    async_client: AsyncClient,
    signed_in_user_in_db: BaseUserDTO,
) -> None:
    ticket_id = await _seed_ticket(user_id=signed_in_user_in_db.id, status_=TicketStatusEnum.BOOKED)

    response = await async_client.delete(url="/api/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    async with SessionPrimary() as session, session.begin():
        ticket = (await session.exec(select(Ticket).where(Ticket.id == ticket_id))).one()
        assert ticket.status == TicketStatusEnum.ANONYMOUS_BOOKED
        assert ticket.user_id is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_invalid_jwt_returns_401(
    async_client: AsyncClient,
    invalid_jwt: None,
) -> None:
    response = await async_client.delete(url="/api/v1/me/", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
