from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from libs.sqlmodel_ext import Session
from sqlalchemy.exc import IntegrityError

from ticketmaster.http.v1.dependencies import validate_lambda_jwt
from ticketmaster.http.v1.schemas import request_schemas, response_schemas
from ticketmaster.http.v1.utils import decode_event_cursor
from ticketmaster.repositories import EventRepository, UserRepository
from ticketmaster.serializers import ToEventResponseSchemaSerializer, ToUserResponseSchemaSerializer

v1_router = APIRouter()


@v1_router.post(
    "/users/",
    status_code=status.HTTP_201_CREATED,
    response_model=response_schemas.UserResponseSchema,
    dependencies=[Depends(validate_lambda_jwt)],
)
async def create_user_fallback(
    payload: request_schemas.CreateUserFallbackRequestSchema,
) -> response_schemas.UserResponseSchema:
    try:
        async with Session() as session, session.begin():
            dto = await UserRepository.create(
                session=session,
                uuid=payload.uuid,
                pool_id=payload.pool_id,
                email=payload.email,
                external_id=payload.external_id,
            )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or pool_id+external_id already exists",
        )

    return ToUserResponseSchemaSerializer.serialize(dto=dto)


@v1_router.get(
    "/events/",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventsPageResponseSchema,
)
async def list_events_page(
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> response_schemas.EventsPageResponseSchema:
    decoded_cursor = decode_event_cursor(cursor=cursor)
    async with Session() as session, session.begin():
        items, next_cursor_pair = await EventRepository.list_after_cursor(
            session=session,
            cursor=decoded_cursor,
            page_size=page_size,
        )

    return response_schemas.EventsPageResponseSchema(
        items=[ToEventResponseSchemaSerializer.serialize(dto=dto) for dto in items],
        page_size=page_size,
        next_cursor=next_cursor_pair.encode() if next_cursor_pair is not None else None,
    )
