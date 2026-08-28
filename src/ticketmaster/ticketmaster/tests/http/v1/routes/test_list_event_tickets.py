"""Endpoint contract tests for GET /api/v1/events/{event_id}/tickets/. Public route — no auth."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.enums import TicketStatusEnum
from ticketmaster.http.v1.schemas.response_schemas import TicketResponseSchema
from ticketmaster.tests.factories import EventFactory, TicketFactory, UserFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_list_event_tickets_when_event_has_no_tickets_returns_empty_list(
    async_client: AsyncClient,
) -> None:
    event = EventFactory()
    await insert(event)

    response = await async_client.get(url=f"/api/v1/events/{event.id}/tickets/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio(loop_scope="session")
async def test_list_event_tickets_when_unknown_event_id_returns_empty_list(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(url="/api/v1/events/999999/tickets/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio(loop_scope="session")
async def test_list_event_tickets_when_event_has_tickets_returns_ordered_by_id(
    async_client: AsyncClient,
) -> None:
    event = EventFactory()
    user = UserFactory()
    await insert(event, user)
    available_ticket = TicketFactory(event_id=event.id)
    reserved_at = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    reserved_ticket = TicketFactory(
        event_id=event.id,
        user_id=user.id,
        status=TicketStatusEnum.RESERVED,
        reserved_at=reserved_at,
    )
    booked_at = datetime(2026, 5, 22, 11, 0, tzinfo=UTC)
    booked_ticket = TicketFactory(
        event_id=event.id,
        user_id=user.id,
        status=TicketStatusEnum.BOOKED,
        reserved_at=reserved_at,
        booked_at=booked_at,
    )
    await insert(available_ticket, reserved_ticket, booked_ticket)

    response = await async_client.get(url=f"/api/v1/events/{event.id}/tickets/")

    assert response.status_code == 200
    items = [TicketResponseSchema(**item) for item in response.json()]
    assert [item.id for item in items] == [available_ticket.id, reserved_ticket.id, booked_ticket.id]
    assert [item.status for item in items] == [
        TicketStatusEnum.AVAILABLE,
        TicketStatusEnum.RESERVED,
        TicketStatusEnum.BOOKED,
    ]
    assert items[1].reserved_at == reserved_at
    assert items[2].booked_at == booked_at


@pytest.mark.asyncio(loop_scope="session")
async def test_list_event_tickets_filters_to_requested_event(
    async_client: AsyncClient,
) -> None:
    requested_event = EventFactory()
    other_event = EventFactory()
    await insert(requested_event, other_event)
    requested_ticket = TicketFactory(event_id=requested_event.id)
    other_ticket = TicketFactory(event_id=other_event.id)
    await insert(requested_ticket, other_ticket)

    response = await async_client.get(url=f"/api/v1/events/{requested_event.id}/tickets/")

    assert response.status_code == 200
    items = [TicketResponseSchema(**item) for item in response.json()]
    assert [item.id for item in items] == [requested_ticket.id]
    assert items[0].event_id == requested_event.id
