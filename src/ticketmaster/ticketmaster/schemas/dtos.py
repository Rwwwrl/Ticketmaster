from datetime import datetime
from typing import Self
from uuid import UUID

from libs.common.schemas.dto import DTO

from ticketmaster.enums import EventTypeEnum
from ticketmaster.models import Event, User


class BaseEventDTO(DTO):
    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime

    @classmethod
    def from_sqlmodel(cls, model: Event) -> Self:
        return cls(**model.model_dump())


class BaseUserDTO(DTO):
    id: int
    uuid: UUID
    pool_id: str
    email: str
    external_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_sqlmodel(cls, model: User) -> Self:
        return cls(**model.model_dump())
