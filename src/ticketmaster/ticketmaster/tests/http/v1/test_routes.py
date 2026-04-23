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
    assert response.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


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
    assert page.total == 2
    assert page.page == 1
    assert page.page_size == 20
    assert [item.id for item in page.items] == [earlier.id, later.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_page_size_is_one(async_client: AsyncClient) -> None:
    first = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC))
    second = EventFactory(start_at=datetime(2026, 5, 2, tzinfo=UTC))
    third = EventFactory(start_at=datetime(2026, 5, 3, tzinfo=UTC))
    await insert(first, second, third)

    r1 = await async_client.get(url="/v1/events/", params={"page": 1, "page_size": 1})
    r2 = await async_client.get(url="/v1/events/", params={"page": 2, "page_size": 1})
    r3 = await async_client.get(url="/v1/events/", params={"page": 3, "page_size": 1})

    p1 = EventsPageResponseSchema(**r1.json())
    p2 = EventsPageResponseSchema(**r2.json())
    p3 = EventsPageResponseSchema(**r3.json())

    assert [r1.status_code, r2.status_code, r3.status_code] == [200, 200, 200]
    assert [p1.items[0].id, p2.items[0].id, p3.items[0].id] == [first.id, second.id, third.id]
    assert p1.total == p2.total == p3.total == 3


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_page_beyond_range(async_client: AsyncClient) -> None:
    await insert(EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC)))

    response = await async_client.get(url="/v1/events/", params={"page": 5, "page_size": 10})

    assert response.status_code == 200
    page = EventsPageResponseSchema(**response.json())
    assert page.items == []
    assert page.total == 1
    assert page.page == 5


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}],
)
async def test_list_events_page_when_params_invalid(
    async_client: AsyncClient,
    params: dict,
) -> None:
    response = await async_client.get(url="/v1/events/", params=params)
    assert response.status_code == 422
