from ticketmaster.http.v1.schemas.response_schemas import EventResponseSchema
from ticketmaster.schemas.dtos import EventDTO


class ToEventResponseSchema:
    @classmethod
    def serialize(cls, dto: EventDTO) -> EventResponseSchema:
        return EventResponseSchema(**dto.model_dump())
