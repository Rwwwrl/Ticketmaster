from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.tests_ext.factories import insert
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.tests.factories import EventFactory


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_when_event_exists(async_client: AsyncClient) -> None:
    event = EventFactory(
        name="Coldplay",
        description="Stadium tour stop",
        type=EventTypeEnum.CONCERT,
        start_at=datetime(2026, 6, 2, 20, 0, tzinfo=UTC),
    )
    await insert(event)

    response = await async_client.get(url=f"/v1/events/{event.id}")

    assert response.status_code == 200
    content = EventResponseSchema(**response.json())
    assert content.id == event.id
    assert content.name == "Coldplay"
    assert content.description == "Stadium tour stop"
    assert content.type == EventTypeEnum.CONCERT
    assert content.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_event_by_id_when_event_does_not_exist(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/v1/events/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Event not found"}
