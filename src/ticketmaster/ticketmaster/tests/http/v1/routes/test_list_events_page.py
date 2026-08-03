from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from redis.asyncio import Redis
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventsPageResponseSchema
from ticketmaster.redis_cache.repositories import NamespaceRepository
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_no_events_in_db(async_client: AsyncClient, redis: Redis) -> None:
    await NamespaceRepository.set(redis=redis)

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})

    assert response.status_code == 200
    assert response.json() == {"items": [], "page_size": 20, "next_cursor": None}


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_events_exist_sorted_by_start_at_then_id(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    await NamespaceRepository.set(redis=redis)

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

    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    assert response.status_code == 200

    page = EventsPageResponseSchema(**response.json())
    assert page.page_size == 20
    assert page.next_cursor is None
    assert [item.id for item in page.items] == [earlier.id, later.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_has_more_pages(async_client: AsyncClient, redis: Redis) -> None:
    await NamespaceRepository.set(redis=redis)

    events = [EventFactory(start_at=datetime(2026, 5, day, tzinfo=UTC)) for day in range(1, 22)]
    await insert(*events)

    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at", "page_size": 20})
    first_page = EventsPageResponseSchema(**first_response.json())

    second_response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "start_at", "cursor": first_page.next_cursor, "page_size": 50},
    )
    second_page = EventsPageResponseSchema(**second_response.json())

    assert [first_response.status_code, second_response.status_code] == [200, 200]
    assert first_page.next_cursor is not None
    assert second_page.next_cursor is None
    assert [item.id for item in first_page.items] == [event.id for event in events[:20]]
    assert [item.id for item in second_page.items] == [events[20].id]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "params",
    [{"page_size": 0}, {"page_size": 10}, {"page_size": 21}, {"page_size": 49}, {"page_size": 51}],
)
async def test_list_events_page_when_params_invalid(
    async_client: AsyncClient,
    params: dict,
) -> None:
    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at", **params})
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_sort_key_is_missing(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/")

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_sort_key_is_rank(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/", params={"sort_key": "rank"})

    assert response.status_code == 400
    assert response.json() == {"detail": "sort_key=rank is not supported for list events"}


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_is_invalid(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at", "cursor": "not-a-cursor"})

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_sorted_by_price(async_client: AsyncClient, redis: Redis) -> None:
    await NamespaceRepository.set(redis=redis)

    cheap = EventFactory(start_at=datetime(2026, 6, 1, tzinfo=UTC), price=Decimal("15.00"))
    mid = EventFactory(start_at=datetime(2026, 5, 1, tzinfo=UTC), price=Decimal("42.50"))
    pricey = EventFactory(start_at=datetime(2026, 4, 1, tzinfo=UTC), price=Decimal("99.00"))
    await insert(pricey, cheap, mid)

    response = await async_client.get(url="/v1/events/", params={"sort_key": "price"})
    assert response.status_code == 200

    page = EventsPageResponseSchema(**response.json())
    assert page.next_cursor is None
    assert [item.id for item in page.items] == [cheap.id, mid.id, pricey.id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_price_cursor_has_more_pages(async_client: AsyncClient, redis: Redis) -> None:
    await NamespaceRepository.set(redis=redis)

    events = [EventFactory(price=Decimal(index)) for index in range(1, 22)]
    await insert(*reversed(events))

    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "price", "page_size": 20})
    first_page = EventsPageResponseSchema(**first_response.json())

    second_response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "price", "cursor": first_page.next_cursor, "page_size": 20},
    )
    second_page = EventsPageResponseSchema(**second_response.json())

    assert [first_response.status_code, second_response.status_code] == [200, 200]
    assert first_page.next_cursor is not None
    assert second_page.next_cursor is None
    assert [item.id for item in first_page.items] == [event.id for event in events[:20]]
    assert [item.id for item in second_page.items] == [events[20].id]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_sort_key_mismatches_returns_400(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    await NamespaceRepository.set(redis=redis)

    events = [EventFactory(start_at=datetime(2026, 5, day, tzinfo=UTC)) for day in range(1, 22)]
    await insert(*events)
    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    first_page = EventsPageResponseSchema(**first_response.json())

    response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "price", "cursor": first_page.next_cursor},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Cursor does not match sort_key"}


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_page_when_cursor_is_tampered_returns_422(
    async_client: AsyncClient,
    redis: Redis,
) -> None:
    await NamespaceRepository.set(redis=redis)

    events = [EventFactory(start_at=datetime(2026, 5, day, tzinfo=UTC)) for day in range(1, 22)]
    await insert(*events)
    first_response = await async_client.get(url="/v1/events/", params={"sort_key": "start_at"})
    first_page = EventsPageResponseSchema(**first_response.json())
    assert first_page.next_cursor is not None

    response = await async_client.get(
        url="/v1/events/",
        params={"sort_key": "start_at", "cursor": f"{first_page.next_cursor[:-2]}aa"},
    )

    assert response.status_code == 422
