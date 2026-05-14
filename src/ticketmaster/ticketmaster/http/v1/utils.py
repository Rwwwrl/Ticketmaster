from fastapi import HTTPException, status

from ticketmaster.repositories import EventCursorDTO


def decode_event_cursor(cursor: str | None) -> EventCursorDTO | None:
    if cursor is None:
        return None

    try:
        return EventCursorDTO.decode(cursor=cursor)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid cursor")
