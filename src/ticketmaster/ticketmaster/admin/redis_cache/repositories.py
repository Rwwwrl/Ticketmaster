from redis.asyncio import Redis

from ticketmaster.redis_cache.repositories import EventCacheRepository


class AdminEventCacheRepository(EventCacheRepository):
    @classmethod
    async def delete_by_id(cls, redis: Redis, _id: int) -> None:
        await redis.delete(cls._event_key(event_id=_id))
