from enum import StrEnum, auto


class EventTypeEnum(StrEnum):
    SPORT = auto()
    THEATER = auto()
    CONCERT = auto()


class TicketStatusEnum(StrEnum):
    AVAILABLE = auto()
    RESERVED = auto()
    BOOKED = auto()
