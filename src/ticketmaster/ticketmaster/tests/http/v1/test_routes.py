from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventsPageResponseSchema
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_no_events_in_db(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page_size": 20, "next_cursor": None}


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_events_exist_sorted_by_start_at_then_id(
    async_client: AsyncClient,
) -> None:
    later = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
    )
    earlier = EventFactory(
        name="Lakers vs Celtics",
        description="NBA regular season game",
        type=EventTypeEnum.SPORT,
        start_at=datetime(2026, 5, 10, 19, 30, tzinfo=UTC),
    )
    await insert(later, earlier)

    response = await async_client.get(url="/v1/events/")
    assert response.status_code == 200

    page = EventsPageResponseSchema(**response.json())
    assert page.page_size == 20
    assert page.next_cursor is None
    assert [item.id for item in page.items] == [earlier.id, later.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_has_more_pages(async_client: AsyncClient) -> None:
    first = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    second = EventFactory(start_at=datetime(2026, 5, 2, tzinfo=UTC))
    third = EventFactory(start_at=datetime(2026, 5, 3, tzinfo=UTC))
    await insert(first, second, third)

    first_response = await async_client.get(url="/v1/events/", params={"page_size": 1})
    first_page = EventsPageResponseSchema(**first_response.json())

    second_response = await async_client.get(
        url="/v1/events/",
        params={"cursor": first_page.next_cursor, "page_size": 1},
    )
    second_page = EventsPageResponseSchema(**second_response.json())

    third_response = await async_client.get(
        url="/v1/events/",
        params={"cursor": second_page.next_cursor, "page_size": 1},
    )
    third_page = EventsPageResponseSchema(**third_response.json())

    assert [first_response.status_code, second_response.status_code, third_response.status_code] == [200, 200, 200]
    assert first_page.next_cursor is not None
    assert second_page.next_cursor is not None
    assert third_page.next_cursor is None
    assert [first_page.items[0].id, second_page.items[0].id, third_page.items[0].id] == [
        first.id,
        second.id,
        third.id,
    ]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "params",
    [{"page_size": 0}, {"page_size": 101}],
)
async def test_list_events_page_when_params_invalid(
    async_client: AsyncClient,
    params: dict,
) -> None:
    response = await async_client.get(url="/v1/events/", params=params)
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_is_invalid(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/", params={"cursor": "not-a-cursor"})

    assert response.status_code == 422
