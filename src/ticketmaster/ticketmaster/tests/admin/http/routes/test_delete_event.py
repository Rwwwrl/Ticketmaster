import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from sqlmodel import select
from ticketmaster.enums import TicketStatusEnum
from ticketmaster.models import Event, Ticket
from ticketmaster.redis_cache.repositories import NamespaceRepository
from ticketmaster.tests.factories import EventFactory, TicketFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_event_when_event_has_no_tickets_returns_204_and_deletes_event(
    async_client: AsyncClient,
    bypass_admin_jwt: None,
) -> None:
    event = EventFactory()
    await insert(event)

    response = await async_client.delete(url=f"/api/admin/events/{event.id}")

    assert response.status_code == 204
    assert response.content == b""

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == event.id))).first()

    assert persisted is None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_event_when_event_not_found_returns_404_and_keeps_namespace(
    async_client: AsyncClient,
    redis: Redis,
    bypass_admin_jwt: None,
) -> None:
    previous_namespace = await NamespaceRepository.set(redis=redis)

    response = await async_client.delete(url="/api/admin/events/999999")
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
    assert current_namespace == previous_namespace


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_event_when_event_has_ticket_returns_409_and_preserves_data_and_namespace(
    async_client: AsyncClient,
    redis: Redis,
    bypass_admin_jwt: None,
) -> None:
    event = EventFactory()
    await insert(event)
    ticket = TicketFactory(event_id=event.id, status=TicketStatusEnum.AVAILABLE)
    await insert(ticket)
    previous_namespace = await NamespaceRepository.set(redis=redis)

    response = await async_client.delete(url=f"/api/admin/events/{event.id}")
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 409
    assert response.json() == {"detail": "Event has tickets"}
    assert current_namespace == previous_namespace

    async with Session() as session, session.begin():
        persisted_event = (await session.exec(select(Event).where(Event.id == event.id))).first()
        persisted_ticket = (await session.exec(select(Ticket).where(Ticket.id == ticket.id))).first()

    assert persisted_event is not None
    assert persisted_ticket is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_event_rotates_list_events_page_namespace(
    async_client: AsyncClient,
    redis: Redis,
    bypass_admin_jwt: None,
) -> None:
    event = EventFactory()
    await insert(event)
    previous_namespace = await NamespaceRepository.set(redis=redis)

    response = await async_client.delete(url=f"/api/admin/events/{event.id}")
    current_namespace = await NamespaceRepository.get(redis=redis)

    assert response.status_code == 204
    assert current_namespace is not None
    assert current_namespace != previous_namespace
