from fastapi import APIRouter, Depends, HTTPException, Response, status
from libs.sqlmodel_ext import Session

from ticketmaster.admin import services
from ticketmaster.admin.exceptions import EventHasTicketsException, UnsupportedS3ObjectException
from ticketmaster.admin.http.dependencies import validate_admin_jwt, validate_s3_events_lambda_jwt
from ticketmaster.admin.http.schemas import request_schemas
from ticketmaster.admin.http.schemas import response_schemas as admin_response_schemas
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
        dto = await services.create_event(
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
            dto = await services.update_event(session=session, event_id=event_id, changes=changes)
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    return ToEventResponseSchemaSerializer.serialize(dto=dto)


@admin_router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(validate_admin_jwt)],
)
async def delete_event(event_id: int) -> Response:
    try:
        async with Session() as session, session.begin():
            await services.delete_event(session=session, event_id=event_id)
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    except EventHasTicketsException:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event has tickets")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/events/{event_id}/trailer/upload-link",
    status_code=status.HTTP_200_OK,
    response_model=admin_response_schemas.EventTrailerUploadLinkResponseSchema,
    dependencies=[Depends(validate_admin_jwt)],
)
async def create_event_trailer_upload_link(
    event_id: int,
) -> admin_response_schemas.EventTrailerUploadLinkResponseSchema:
    try:
        async with Session() as session, session.begin():
            return await services.create_event_trailer_upload_link(session=session, event_id=event_id)
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")


@admin_router.post(
    "/s3-events",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(validate_s3_events_lambda_jwt)],
)
async def process_s3_event(payload: request_schemas.S3EventRequestSchema) -> Response:
    try:
        async with Session() as session, session.begin():
            await services.process_s3_event(
                session=session,
                bucket=payload.bucket,
                key=payload.key,
                metadata=payload.metadata,
            )
    except UnsupportedS3ObjectException:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unsupported s3 object")
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
