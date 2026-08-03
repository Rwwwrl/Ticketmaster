from libs.common.services import create_service_cursor, encode_service_cursor
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.cursors import EventCursorBodyDTO, EventCursorDTO, EventDBCursorDTO
from ticketmaster.repositories import EventRepository
from ticketmaster.schemas.dtos import BaseEventDTO
from ticketmaster.settings import settings


async def search_events(
    session: AsyncSession,
    q: str,
    cursor: EventCursorDTO | None,
    page_size: int,
) -> tuple[list[BaseEventDTO], str | None]:
    page_index = cursor.body.page_index if cursor is not None else 0

    db_cursor = (
        EventDBCursorDTO(
            sort_key=cursor.body.sort_key,
            sort_key_value=cursor.body.sort_key_value,
            id=cursor.body.id,
        )
        if cursor is not None
        else None
    )

    items, next_cursor = await EventRepository.search_after_cursor(
        session=session,
        q=q,
        cursor=db_cursor,
        page_size=page_size,
    )

    next_cursor = (
        encode_service_cursor(
            cursor=create_service_cursor(
                cursor_class=EventCursorDTO,
                body=EventCursorBodyDTO(
                    sort_key=next_cursor.sort_key,
                    sort_key_value=next_cursor.sort_key_value,
                    id=next_cursor.id,
                    page_index=page_index + 1,
                ),
                secret=settings.secret,
            ),
        )
        if next_cursor is not None
        else None
    )

    return items, next_cursor
