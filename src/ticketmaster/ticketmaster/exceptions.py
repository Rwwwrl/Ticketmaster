from libs.redis_ext import CacheDocumentNotFoundException
from libs.sqlmodel_ext import NotFoundException


class EventNotFoundException(NotFoundException):
    pass


class UserNotFoundException(NotFoundException):
    pass


class EventCacheDocumentNotFoundException(CacheDocumentNotFoundException):
    pass
