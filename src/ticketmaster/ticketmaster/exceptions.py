from libs.sqlmodel_ext import NotFoundException


class EventNotFoundException(NotFoundException):
    """Raised when an event lookup returns no row."""


class UserNotFoundException(NotFoundException):
    """Raised when a user lookup returns no row."""
