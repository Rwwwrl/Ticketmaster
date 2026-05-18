"""Endpoint contract tests for POST /v1/events/{event_id}/tickets/{ticket_id}/{reserve,book}.
Auth dependency is bypassed via dependency_overrides; JWT validation has its own coverage
in test_dependencies.py."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from libs.datetime_ext.utils import utc_now
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from ticketmaster.enums import TicketStatusEnum
from ticketmaster.http.v1.dependencies import validate_user_jwt
from ticketmaster.models import User
from ticketmaster.repositories import TicketRepository
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.tests.factories import EventFactory, TicketFactory, UserFactory


@pytest.fixture
def override_user_jwt(fastapi_app: FastAPI) -> Iterator[User]:
    user = UserFactory()

    async def _override() -> BaseUserDTO:
        return BaseUserDTO.from_sqlmodel(model=user)

    fastapi_app.dependency_overrides[validate_user_jwt] = _override
    yield user
    fastapi_app.dependency_overrides.clear()


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_ticket_when_available_returns_204(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    ticket = TicketFactory(event_id=event.id)
    await insert(ticket)

    before = utc_now()
    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/reserve")
    after = utc_now()

    assert response.status_code == 204
    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)
    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.user_id == override_user_jwt.id
    assert before <= persisted.reserved_at <= after
    assert before <= persisted.updated_at <= after


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_ticket_when_reserved_fresh_by_other_user_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    other_user = UserFactory()
    event = EventFactory()
    await insert(override_user_jwt, other_user, event)
    other_reserved_at = utc_now() - timedelta(minutes=1)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=other_user.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=other_reserved_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/reserve")

    assert response.status_code == 400
    assert response.json() == {"detail": "Ticket not reservable"}
    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)
    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.user_id == other_user.id
    assert persisted.reserved_at == other_reserved_at


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_ticket_when_reserved_expired_returns_204(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    other_user = UserFactory()
    event = EventFactory()
    await insert(override_user_jwt, other_user, event)
    expired_at = utc_now() - timedelta(minutes=11)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=other_user.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=expired_at,
    )
    await insert(ticket)

    before = utc_now()
    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/reserve")
    after = utc_now()

    assert response.status_code == 204
    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)
    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.user_id == override_user_jwt.id
    assert before <= persisted.reserved_at <= after


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_ticket_when_booked_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    other_user = UserFactory()
    event = EventFactory()
    await insert(override_user_jwt, other_user, event)
    booked_at = datetime(2026, 1, 1, tzinfo=UTC)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=other_user.id,
        status=TicketStatusEnum.BOOKED,
        booked_at=booked_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/reserve")

    assert response.status_code == 400
    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)
    assert persisted.status == TicketStatusEnum.BOOKED
    assert persisted.user_id == other_user.id
    assert persisted.booked_at == booked_at


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_ticket_when_ticket_does_not_exist_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/999999/reserve")

    assert response.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_fresh_reservation_by_caller_returns_204(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    reserved_at = utc_now() - timedelta(minutes=1)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=override_user_jwt.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=reserved_at,
    )
    await insert(ticket)

    before = utc_now()
    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")
    after = utc_now()

    assert response.status_code == 204

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.BOOKED
    assert persisted.user_id == override_user_jwt.id
    assert persisted.reserved_at == reserved_at
    assert before <= persisted.booked_at <= after
    assert before <= persisted.updated_at <= after


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_reservation_expired_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    expired_at = utc_now() - timedelta(minutes=11)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=override_user_jwt.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=expired_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")

    assert response.status_code == 400
    assert response.json() == {"detail": "Ticket not bookable"}

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.booked_at is None
    assert persisted.reserved_at == expired_at


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_reserved_by_other_user_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    other_user = UserFactory()
    event = EventFactory()
    await insert(override_user_jwt, other_user, event)
    other_reserved_at = utc_now() - timedelta(minutes=1)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=other_user.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=other_reserved_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")

    assert response.status_code == 400

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.user_id == other_user.id
    assert persisted.booked_at is None


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_ticket_is_available_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    ticket = TicketFactory(event_id=event.id)
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")

    assert response.status_code == 400

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.AVAILABLE
    assert persisted.user_id is None
    assert persisted.booked_at is None


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_already_booked_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    booked_at = datetime(2026, 1, 1, tzinfo=UTC)
    ticket = TicketFactory(
        event_id=event.id,
        user_id=override_user_jwt.id,
        status=TicketStatusEnum.BOOKED,
        booked_at=booked_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")

    assert response.status_code == 400

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.BOOKED
    assert persisted.booked_at == booked_at


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_path_event_id_does_not_match_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    real_event = EventFactory()
    wrong_event = EventFactory()
    await insert(override_user_jwt, real_event, wrong_event)
    reserved_at = utc_now() - timedelta(minutes=1)
    ticket = TicketFactory(
        event_id=real_event.id,
        user_id=override_user_jwt.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=reserved_at,
    )
    await insert(ticket)

    response = await async_client.post(url=f"/v1/events/{wrong_event.id}/tickets/{ticket.id}/book")

    assert response.status_code == 400

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.RESERVED
    assert persisted.booked_at is None


@pytest.mark.asyncio(loop_scope="session")
async def test_book_ticket_when_ticket_does_not_exist_returns_400(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)

    response = await async_client.post(url=f"/v1/events/{event.id}/tickets/999999/book")

    assert response.status_code == 400


@pytest.mark.asyncio(loop_scope="session")
async def test_reserve_then_book_two_step_flow_returns_204(
    async_client: AsyncClient,
    override_user_jwt: User,
) -> None:
    event = EventFactory()
    await insert(override_user_jwt, event)
    ticket = TicketFactory(event_id=event.id)
    await insert(ticket)

    reserve_response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/reserve")
    assert reserve_response.status_code == 204

    book_response = await async_client.post(url=f"/v1/events/{event.id}/tickets/{ticket.id}/book")
    assert book_response.status_code == 204

    async with Session() as session, session.begin():
        persisted = await TicketRepository.get_by_id(session=session, ticket_id=ticket.id)

    assert persisted.status == TicketStatusEnum.BOOKED
    assert persisted.user_id == override_user_jwt.id
    assert persisted.reserved_at is not None
    assert persisted.booked_at is not None
