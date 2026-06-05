import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.http.v1.schemas.response_schemas import EventsPageResponseSchema
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_no_matches(async_client: AsyncClient) -> None:
    await insert(EventFactory(name="Lakers vs Celtics", description="NBA regular season"))

    response = await async_client.get(url="/v1/events/search", params={"q": "coldplay"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "page_size": 20, "next_cursor": None}


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_match_in_name(async_client: AsyncClient) -> None:
    match = EventFactory(name="Coldplay Live", description="Tour stop")
    noise = EventFactory(name="Lakers vs Celtics", description="NBA game")
    await insert(match, noise)

    response = await async_client.get(url="/v1/events/search", params={"q": "coldplay"})

    assert response.status_code == 200
    page = EventsPageResponseSchema(**response.json())
    assert [item.id for item in page.items] == [match.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_match_in_description(async_client: AsyncClient) -> None:
    match = EventFactory(name="Friday concert", description="Held at Wembley stadium")
    noise = EventFactory(name="Lakers vs Celtics", description="NBA game")
    await insert(match, noise)

    response = await async_client.get(url="/v1/events/search", params={"q": "stadium"})

    assert response.status_code == 200
    page = EventsPageResponseSchema(**response.json())
    assert [item.id for item in page.items] == [match.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_name_outranks_description(async_client: AsyncClient) -> None:
    name_match = EventFactory(name="Rock festival", description="Outdoor venue")
    description_match = EventFactory(name="Summer Gala", description="A rock-themed evening")
    await insert(name_match, description_match)

    response = await async_client.get(url="/v1/events/search", params={"q": "rock"})

    assert response.status_code == 200
    page = EventsPageResponseSchema(**response.json())
    assert [item.id for item in page.items] == [name_match.id, description_match.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_cursor_walk(async_client: AsyncClient) -> None:
    first = EventFactory(name="Coldplay world tour", description="A")
    second = EventFactory(name="Coldplay tribute", description="B")
    third = EventFactory(name="Symphony night", description="Coldplay covers")
    await insert(first, second, third)

    first_response = await async_client.get(url="/v1/events/search", params={"q": "coldplay", "page_size": 1})
    first_page = EventsPageResponseSchema(**first_response.json())

    second_response = await async_client.get(
        url="/v1/events/search",
        params={"q": "coldplay", "page_size": 1, "cursor": first_page.next_cursor},
    )
    second_page = EventsPageResponseSchema(**second_response.json())

    third_response = await async_client.get(
        url="/v1/events/search",
        params={"q": "coldplay", "page_size": 1, "cursor": second_page.next_cursor},
    )
    third_page = EventsPageResponseSchema(**third_response.json())

    assert [first_response.status_code, second_response.status_code, third_response.status_code] == [200, 200, 200]

    assert first_page.next_cursor is not None
    assert second_page.next_cursor is not None
    assert third_page.next_cursor is None

    assert {first_page.items[0].id, second_page.items[0].id, third_page.items[0].id} == {first.id, second.id, third.id}
