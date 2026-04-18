from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_when_no_events_in_db(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio(loop_scope="session")
async def test_list_events_when_events_exist(async_client: AsyncClient) -> None:
    sport_event = EventFactory(
        name="Lakers vs Celtics",
        description="NBA regular season game",
        type=EventTypeEnum.SPORT,
        start_at=datetime(2026, 5, 10, 19, 30, tzinfo=timezone.utc),
    )
    concert_event = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=timezone.utc),
    )
    await insert(sport_event, concert_event)

    response = await async_client.get(url="/v1/events/")

    assert response.status_code == 200
    body = [EventResponseSchema(**item) for item in response.json()]
    by_id = {schema.id: schema for schema in body}

    assert by_id.keys() == {sport_event.id, concert_event.id}
    assert by_id[sport_event.id] == EventResponseSchema(
        id=sport_event.id,
        name=sport_event.name,
        description=sport_event.description,
        type=sport_event.type,
        start_at=sport_event.start_at,
    )
    assert by_id[concert_event.id] == EventResponseSchema(
        id=concert_event.id,
        name=concert_event.name,
        description=concert_event.description,
        type=concert_event.type,
        start_at=concert_event.start_at,
    )
