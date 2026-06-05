"""Endpoint contract tests for DELETE /v1/me/. Auth dependency is bypassed via dependency_overrides;
Cognito client is monkey-patched on the shared aws_session singleton."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from libs.aws.session import aws_session
from libs.sqlmodel_ext import Session
from sqlmodel import select
from ticketmaster.enums import TicketStatusEnum
from ticketmaster.http.v1.dependencies import validate_user_jwt
from ticketmaster.models import Ticket, User
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.tests.factories import EventFactory, TicketFactory, UserFactory


@pytest_asyncio.fixture
async def signed_in_user_in_db(fastapi_app: FastAPI) -> AsyncIterator[BaseUserDTO]:
    async with Session() as session, session.begin():
        user = UserFactory.build()
        session.add(user)
        await session.flush()
        await session.refresh(user)
        dto = BaseUserDTO.from_sqlmodel(model=user)

    fastapi_app.dependency_overrides[validate_user_jwt] = lambda: dto
    yield dto
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def mock_cognito(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    cognito = AsyncMock()
    cognito.exceptions.UserNotFoundException = type("UserNotFoundException", (Exception,), {})

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=cognito)
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(aws_session, "client", MagicMock(return_value=cm))
    return cognito


async def _seed_ticket(*, user_id: int, status_: TicketStatusEnum) -> int:
    async with Session() as session, session.begin():
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
    response = await async_client.delete(url="/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    mock_cognito.admin_delete_user.assert_awaited_once_with(
        UserPoolId=signed_in_user_in_db.pool_id,
        Username=signed_in_user_in_db.cognito_username,
    )

    async with Session() as session, session.begin():
        result = await session.exec(select(User).where(User.id == signed_in_user_in_db.id))
        assert result.first() is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_user_has_reserved_tickets_releases_them(
    async_client: AsyncClient,
    signed_in_user_in_db: BaseUserDTO,
    mock_cognito: AsyncMock,
) -> None:
    ticket_id = await _seed_ticket(user_id=signed_in_user_in_db.id, status_=TicketStatusEnum.RESERVED)

    response = await async_client.delete(url="/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    async with Session() as session, session.begin():
        ticket = (await session.exec(select(Ticket).where(Ticket.id == ticket_id))).one()
        assert ticket.status == TicketStatusEnum.AVAILABLE
        assert ticket.user_id is None
        assert ticket.reserved_at is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_user_has_booked_tickets_marks_anonymous_booked(
    async_client: AsyncClient,
    signed_in_user_in_db: BaseUserDTO,
    mock_cognito: AsyncMock,
) -> None:
    ticket_id = await _seed_ticket(user_id=signed_in_user_in_db.id, status_=TicketStatusEnum.BOOKED)

    response = await async_client.delete(url="/v1/me/", headers={"Authorization": "Bearer fake"})

    assert response.status_code == 204
    async with Session() as session, session.begin():
        ticket = (await session.exec(select(Ticket).where(Ticket.id == ticket_id))).one()
        assert ticket.status == TicketStatusEnum.ANONYMOUS_BOOKED
        assert ticket.user_id is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_me_when_invalid_jwt_returns_401(
    async_client: AsyncClient,
    invalid_jwt: None,
) -> None:
    response = await async_client.delete(url="/v1/me/", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
