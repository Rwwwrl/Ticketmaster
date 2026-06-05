from enum import StrEnum, auto


class EventTypeEnum(StrEnum):
    SPORT = auto()
    THEATER = auto()
    CONCERT = auto()


class TicketStatusEnum(StrEnum):
    AVAILABLE = auto()
    RESERVED = auto()
    BOOKED = auto()
    ANONYMOUS_BOOKED = auto()


class CurrencyEnum(StrEnum):
    EUR = "EUR"
    USD = "USD"


class EventSortKeyEnum(StrEnum):
    START_AT = auto()
    PRICE = auto()
