from enum import StrEnum, auto


class EnvironmentEnum(StrEnum):
    DEV = auto()
    TEST = auto()
    PROD = auto()
    CICD = auto()


class AppNameEnum(StrEnum):
    TICKETMASTER = auto()


class ServiceNameEnum(StrEnum):
    TICKETMASTER = auto()
