from datetime import datetime
from typing import Self

from libs.common.schemas.dto import DTO

from ticketmaster.enums import EventTypeEnum
from ticketmaster.models import Event


class EventDTO(DTO):
    id: int
    name: str
    description: str
    type: EventTypeEnum
    start_at: datetime

    @classmethod
    def from_sqlmodel(cls, model: Event) -> Self:
        return cls(**model.model_dump(include=set(cls.model_fields)))
