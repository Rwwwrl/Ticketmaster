from ticketmaster.http.v1.schemas.response_schemas import (
    EventResponseSchema,
    TicketResponseSchema,
    UserResponseSchema,
)
from ticketmaster.schemas.dtos import BaseEventDTO, BaseTicketDTO, BaseUserDTO


class ToEventResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseEventDTO) -> EventResponseSchema:
        return EventResponseSchema(**dto.model_dump())


class ToTicketResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseTicketDTO) -> TicketResponseSchema:
        return TicketResponseSchema(**dto.model_dump())


class ToUserResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseUserDTO) -> UserResponseSchema:
        return UserResponseSchema(**dto.model_dump())
