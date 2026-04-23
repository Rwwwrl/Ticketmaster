from typing import Annotated

from fastapi import APIRouter, Query, status
from libs.sqlmodel_ext import Session

from ticketmaster.http.v1.schemas import response_schemas
from ticketmaster.repositories import EventRepository
from ticketmaster.serializers import ToEventResponseSchema

v1_router = APIRouter()


@v1_router.get(
    "/events/",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventsPageResponseSchema,
)
async def list_events_page(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> response_schemas.EventsPageResponseSchema:
    async with Session() as session, session.begin():
        items, total = await EventRepository.get_all_paginated(
            session=session,
            page=page,
            page_size=page_size,
        )

    return response_schemas.EventsPageResponseSchema(
        items=[ToEventResponseSchema.serialize(dto=dto) for dto in items],
        page=page,
        page_size=page_size,
        total=total,
    )
