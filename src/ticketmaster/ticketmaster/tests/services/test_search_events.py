import pytest
from libs.common.services import decode_service_cursor
from libs.sqlmodel_ext import Session
from libs.tests_ext.factories import insert
from sqlalchemy.ext.asyncio import AsyncEngine
from ticketmaster.cursors import EventCursorDTO
from ticketmaster.services.search_events import search_events
from ticketmaster.settings import settings
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_no_matches(sqlmodel_engine: AsyncEngine) -> None:
    await insert(EventFactory(name="Lakers vs Celtics", description="NBA regular season"))

    async with Session() as session, session.begin():
        items, next_cursor = await search_events(
            session=session,
            q="coldplay",
            cursor=None,
            page_size=20,
        )

    assert items == []
    assert next_cursor is None


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_match_in_name(sqlmodel_engine: AsyncEngine) -> None:
    match = EventFactory(name="Coldplay Live", description="Tour stop")
    noise = EventFactory(name="Lakers vs Celtics", description="NBA game")
    await insert(match, noise)

    async with Session() as session, session.begin():
        items, next_cursor = await search_events(
            session=session,
            q="coldplay",
            cursor=None,
            page_size=20,
        )

    assert [item.id for item in items] == [match.id]
    assert next_cursor is None


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_match_in_description(sqlmodel_engine: AsyncEngine) -> None:
    match = EventFactory(name="Friday concert", description="Held at Wembley stadium")
    noise = EventFactory(name="Lakers vs Celtics", description="NBA game")
    await insert(match, noise)

    async with Session() as session, session.begin():
        items, next_cursor = await search_events(
            session=session,
            q="stadium",
            cursor=None,
            page_size=20,
        )

    assert [item.id for item in items] == [match.id]
    assert next_cursor is None


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_name_outranks_description(sqlmodel_engine: AsyncEngine) -> None:
    name_match = EventFactory(name="Rock festival", description="Outdoor venue")
    description_match = EventFactory(name="Summer Gala", description="A rock-themed evening")
    await insert(name_match, description_match)

    async with Session() as session, session.begin():
        items, next_cursor = await search_events(
            session=session,
            q="rock",
            cursor=None,
            page_size=20,
        )

    assert [item.id for item in items] == [name_match.id, description_match.id]
    assert next_cursor is None


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_cursor_walk(sqlmodel_engine: AsyncEngine) -> None:
    first = EventFactory(name="Coldplay world tour", description="A")
    second = EventFactory(name="Coldplay tribute", description="B")
    third = EventFactory(name="Symphony night", description="Coldplay covers")
    await insert(first, second, third)

    async with Session() as session, session.begin():
        first_items, first_next_cursor = await search_events(
            session=session,
            q="coldplay",
            cursor=None,
            page_size=1,
        )

    assert first_next_cursor is not None
    first_cursor = decode_service_cursor(
        encoded_cursor=first_next_cursor,
        cursor_class=EventCursorDTO,
        secret=settings.secret,
    )

    async with Session() as session, session.begin():
        second_items, second_next_cursor = await search_events(
            session=session,
            q="coldplay",
            cursor=first_cursor,
            page_size=1,
        )

    assert second_next_cursor is not None
    second_cursor = decode_service_cursor(
        encoded_cursor=second_next_cursor,
        cursor_class=EventCursorDTO,
        secret=settings.secret,
    )

    async with Session() as session, session.begin():
        third_items, third_next_cursor = await search_events(
            session=session,
            q="coldplay",
            cursor=second_cursor,
            page_size=1,
        )

    assert third_next_cursor is None
    assert {first_items[0].id, second_items[0].id, third_items[0].id} == {first.id, second.id, third.id}
