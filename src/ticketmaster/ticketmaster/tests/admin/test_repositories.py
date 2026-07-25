import pytest
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from ticketmaster.admin.repositories import AdminTicketRepository
from ticketmaster.tests.factories import EventFactory, TicketFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_ticket_repository_exists_when_no_tickets_returns_false(sqlmodel_engine: AsyncEngine) -> None:
    async with Session() as session, session.begin():
        result = await AdminTicketRepository.exists(session=session)

    assert result is False


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_ticket_repository_exists_when_event_id_matches_returns_true(sqlmodel_engine: AsyncEngine) -> None:
    event = EventFactory()
    await insert(event)
    await insert(TicketFactory(event_id=event.id))

    async with Session() as session, session.begin():
        result = await AdminTicketRepository.exists(session=session, event_id=event.id)

    assert result is True


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_ticket_repository_exists_when_event_id_does_not_match_returns_false(
    sqlmodel_engine: AsyncEngine,
) -> None:
    event = EventFactory()
    other_event = EventFactory()
    await insert(event)
    await insert(other_event)
    await insert(TicketFactory(event_id=event.id))

    async with Session() as session, session.begin():
        result = await AdminTicketRepository.exists(session=session, event_id=other_event.id)

    assert result is False


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_ticket_repository_exists_without_filters_when_ticket_exists_returns_true(
    sqlmodel_engine: AsyncEngine,
) -> None:
    event = EventFactory()
    await insert(event)
    await insert(TicketFactory(event_id=event.id))

    async with Session() as session, session.begin():
        result = await AdminTicketRepository.exists(session=session)

    assert result is True
