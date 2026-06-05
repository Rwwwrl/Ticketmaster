from fastapi import APIRouter, Depends, HTTPException, status
from libs.sqlmodel_ext import Session

from ticketmaster.admin.http.dependencies import validate_admin_jwt
from ticketmaster.admin.http.schemas import request_schemas
from ticketmaster.admin.services import AdminEventService
from ticketmaster.exceptions import EventNotFoundException
from ticketmaster.http.v1.schemas import response_schemas
from ticketmaster.serializers import ToEventResponseSchemaSerializer

admin_router = APIRouter()


@admin_router.post(
    "/events/",
    status_code=status.HTTP_201_CREATED,
    response_model=response_schemas.EventResponseSchema,
    dependencies=[Depends(validate_admin_jwt)],
)
async def create_event(
    payload: request_schemas.CreateEventRequestSchema,
) -> response_schemas.EventResponseSchema:
    async with Session() as session, session.begin():
        dto = await AdminEventService.create_event(
            session=session,
            name=payload.name,
            description=payload.description,
            type=payload.type,
            start_at=payload.start_at,
            price=payload.price,
            currency=payload.currency,
        )

    return ToEventResponseSchemaSerializer.serialize(dto=dto)


@admin_router.patch(
    "/events/{event_id}",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventResponseSchema,
    dependencies=[Depends(validate_admin_jwt)],
)
async def update_event(
    event_id: int,
    payload: request_schemas.UpdateEventRequestSchema,
) -> response_schemas.EventResponseSchema:
    changes = payload.model_dump(exclude_unset=True)

    try:
        async with Session() as session, session.begin():
            dto = await AdminEventService.update_event(session=session, event_id=event_id, changes=changes)
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    return ToEventResponseSchemaSerializer.serialize(dto=dto)
