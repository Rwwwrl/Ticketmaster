from libs.aws.utils import build_s3_object_public_url

from ticketmaster.http.v1.schemas.response_schemas import (
    EventResponseSchema,
    TicketResponseSchema,
    UserResponseSchema,
)
from ticketmaster.schemas.dtos import BaseEventDTO, BaseTicketDTO, BaseUserDTO
from ticketmaster.settings import settings


class ToEventResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseEventDTO) -> EventResponseSchema:
        data = dto.model_dump(exclude={"trailer_bucket", "trailer_key"})

        trailer_url = None
        if all([dto.trailer_bucket, dto.trailer_key]):
            trailer_url = build_s3_object_public_url(
                region=settings.aws_region,
                bucket=dto.trailer_bucket,
                key=dto.trailer_key,
            )

        return EventResponseSchema(**data, trailer_url=trailer_url)


class ToTicketResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseTicketDTO) -> TicketResponseSchema:
        return TicketResponseSchema(**dto.model_dump())


class ToUserResponseSchemaSerializer:
    @classmethod
    def serialize(cls, dto: BaseUserDTO) -> UserResponseSchema:
        return UserResponseSchema(**dto.model_dump())
