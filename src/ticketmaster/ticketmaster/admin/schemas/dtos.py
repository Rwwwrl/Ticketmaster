from uuid import UUID

from libs.common.schemas.dto import DTO
from pydantic import Field


class EventTrailerCreatedMetaDTO(DTO):
    logical_identity: UUID = Field(alias="logical-identity")


class EventTrailerCreatedDTO(DTO):
    bucket: str
    key: str
    meta: EventTrailerCreatedMetaDTO
