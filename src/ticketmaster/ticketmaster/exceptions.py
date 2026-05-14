from libs.sqlmodel_ext import NotFoundException


class UserNotFoundException(NotFoundException):
    """Raised when a user lookup returns no row."""
