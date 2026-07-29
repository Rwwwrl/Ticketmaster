from libs.redis_ext.cache import BaseServiceCache


class ListEventsPageServiceCache(BaseServiceCache):
    events_ids: list[int]
    next_cursor: str | None
