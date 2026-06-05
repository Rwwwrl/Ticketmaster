from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from libs.datetime_ext.utils import utc_now
from libs.sqlmodel_ext import Session
from sqlalchemy.exc import IntegrityError

from ticketmaster import consts
from ticketmaster.cursors import EventCursorDTO
from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.exceptions import CursorSortKeyMismatchException, EventNotFoundException
from ticketmaster.http.v1.dependencies import (
    decode_event_cursor,
    decode_event_search_cursor,
    validate_lambda_jwt,
    validate_user_jwt,
)
from ticketmaster.http.v1.schemas import request_schemas, response_schemas
from ticketmaster.repositories import EventRepository, TicketRepository, UserRepository
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.serializers import (
    ToEventResponseSchemaSerializer,
    ToTicketResponseSchemaSerializer,
    ToUserResponseSchemaSerializer,
)
from ticketmaster.services import EventService, UserService

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
                cognito_username=payload.cognito_username,
            )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email or pool_id+cognito_username already exists",
        )

    return ToUserResponseSchemaSerializer.serialize(dto=dto)


@v1_router.get(
    "/me/",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.UserResponseSchema,
)
async def get_me(
    user: Annotated[BaseUserDTO, Depends(validate_user_jwt)],
) -> response_schemas.UserResponseSchema:
    return ToUserResponseSchemaSerializer.serialize(dto=user)


@v1_router.delete("/me/", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    user: Annotated[BaseUserDTO, Depends(validate_user_jwt)],
) -> Response:
    async with Session() as session, session.begin():
        await UserService.delete_user(session=session, user=user)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@v1_router.get(
    "/events/",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventsPageResponseSchema,
)
async def list_events_page(
    sort_key: Annotated[EventSortKeyEnum, Query()],
    cursor: Annotated[EventCursorDTO | None, Depends(decode_event_cursor)],
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> response_schemas.EventsPageResponseSchema:
    try:
        async with Session() as session, session.begin():
            items, next_cursor_pair = await EventService.list_events_page(
                session=session,
                sort_key=sort_key,
                cursor=cursor,
                page_size=page_size,
            )
    except CursorSortKeyMismatchException:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cursor does not match sort_key")

    return response_schemas.EventsPageResponseSchema(
        items=[ToEventResponseSchemaSerializer.serialize(dto=dto) for dto in items],
        page_size=page_size,
        next_cursor=next_cursor_pair.encode() if next_cursor_pair is not None else None,
    )


@v1_router.get(
    "/events/search",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventsPageResponseSchema,
)
async def search_events(
    q: Annotated[str, Query(min_length=1, max_length=200)],
    cursor: Annotated[str | None, Query()] = None,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> response_schemas.EventsPageResponseSchema:
    decoded_cursor = decode_event_search_cursor(cursor=cursor)

    async with Session() as session, session.begin():
        items, next_cursor_pair = await EventRepository.search_after_cursor(
            session=session,
            q=q,
            cursor=decoded_cursor,
            page_size=page_size,
        )

    return response_schemas.EventsPageResponseSchema(
        items=[ToEventResponseSchemaSerializer.serialize(dto=dto) for dto in items],
        page_size=page_size,
        next_cursor=next_cursor_pair.encode() if next_cursor_pair is not None else None,
    )


@v1_router.get(
    "/events/{event_id}",
    status_code=status.HTTP_200_OK,
    response_model=response_schemas.EventResponseSchema,
)
async def get_event_by_id(event_id: int) -> response_schemas.EventResponseSchema:
    try:
        async with Session() as session, session.begin():
            event = await EventService.get_event_by_id(session=session, _id=event_id)
    except EventNotFoundException:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    return ToEventResponseSchemaSerializer.serialize(dto=event)


@v1_router.get(
    "/events/{event_id}/tickets/",
    status_code=status.HTTP_200_OK,
    response_model=list[response_schemas.TicketResponseSchema],
)
async def list_event_tickets(event_id: int) -> list[response_schemas.TicketResponseSchema]:
    async with Session() as session, session.begin():
        items = await TicketRepository.get_all_by_event_id(session=session, event_id=event_id)

    return [ToTicketResponseSchemaSerializer.serialize(dto=dto) for dto in items]


@v1_router.post(
    "/events/{event_id}/tickets/{ticket_id}/reserve",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reserve_ticket(
    event_id: int,
    ticket_id: int,
    user: Annotated[BaseUserDTO, Depends(validate_user_jwt)],
) -> None:
    async with Session() as session, session.begin():
        ticket_reserved = await TicketRepository.reserve(
            session=session,
            event_id=event_id,
            ticket_id=ticket_id,
            user_id=user.id,
            now=utc_now(),
            reservation_ttl=consts.RESERVATION_TTL,
        )

    if not ticket_reserved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket not reservable")

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@v1_router.post(
    "/events/{event_id}/tickets/{ticket_id}/book",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def book_ticket(
    event_id: int,
    ticket_id: int,
    user: Annotated[BaseUserDTO, Depends(validate_user_jwt)],
) -> None:
    async with Session() as session, session.begin():
        ticket_booked = await TicketRepository.book(
            session=session,
            event_id=event_id,
            ticket_id=ticket_id,
            user_id=user.id,
            now=utc_now(),
            reservation_ttl=consts.RESERVATION_TTL,
        )

    if not ticket_booked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ticket not bookable")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
