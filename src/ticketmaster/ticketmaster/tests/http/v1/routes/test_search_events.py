import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.http.v1.schemas.response_schemas import EventsPageResponseSchema
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_search_events_when_match_returns_page_shape(async_client: AsyncClient) -> None:
    match = EventFactory(name="Coldplay Live", description="Tour stop")
    noise = EventFactory(name="Lakers vs Celtics", description="NBA game")
    await insert(match, noise)

    response = await async_client.get(url="/v1/events/search", params={"q": "coldplay", "sort_key": "rank"})

    assert response.status_code == 200
    page = EventsPageResponseSchema(**response.json())
    assert page.page_size == 20
    assert page.next_cursor is None
    assert [item.id for item in page.items] == [match.id]
