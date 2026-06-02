from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from libs.sqlmodel_ext import Session
from sqlmodel import select
from ticketmaster.enums import EventTypeEnum
from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.models import Event


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_when_valid_payload_returns_201_and_persists(
    async_client: AsyncClient, bypass_admin_jwt: None
) -> None:
    payload = {
        "name": "Coldplay",
        "description": "Stadium tour stop",
        "type": EventTypeEnum.CONCERT,
        "start_at": datetime(2026, 6, 2, 20, 0, tzinfo=UTC).isoformat(),
    }

    response = await async_client.post(url="/admin/events/", json=payload)

    assert response.status_code == 201
    body = EventResponseSchema(**response.json())
    assert body.id is not None
    assert body.name == payload["name"]
    assert body.description == payload["description"]
    assert body.type == EventTypeEnum.CONCERT
    assert body.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)

    async with Session() as session, session.begin():
        persisted = (await session.exec(select(Event).where(Event.id == body.id))).first()

        assert persisted is not None
        assert persisted.name == payload["name"]
        assert persisted.description == payload["description"]
        assert persisted.type == EventTypeEnum.CONCERT
        assert persisted.start_at == datetime(2026, 6, 2, 20, 0, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_create_event_when_missing_field_returns_422(async_client: AsyncClient, bypass_admin_jwt: None) -> None:
    payload = {
        "name": "Coldplay",
        "type": EventTypeEnum.CONCERT,
        "start_at": datetime(2026, 6, 2, 20, 0, tzinfo=UTC).isoformat(),
    }

    response = await async_client.post(url="/admin/events/", json=payload)

    assert response.status_code == 422
