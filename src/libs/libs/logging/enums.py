from enum import StrEnum, auto


class LogLevelEnum(StrEnum):
    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


class ProcessTypeEnum(StrEnum):
    FASTAPI = auto()
