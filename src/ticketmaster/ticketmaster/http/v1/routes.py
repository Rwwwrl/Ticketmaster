from fastapi import APIRouter, status
from libs.sqlmodel_ext import Session

from ticketmaster.http.v1.schemas import response_schemas
from ticketmaster.repositories import EventRepository
from ticketmaster.serializers import ToEventResponseSchema

v1_router = APIRouter()


@v1_router.get(
    "/events/",
    status_code=status.HTTP_200_OK,
    response_model=list[response_schemas.EventResponseSchema],
)
async def list_events() -> list[response_schemas.EventResponseSchema]:
    async with Session() as session, session.begin():
        events = await EventRepository.get_all(session=session)

    return [ToEventResponseSchema.serialize(dto=dto) for dto in events]
