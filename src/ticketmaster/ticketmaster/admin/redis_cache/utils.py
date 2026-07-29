from libs.redis_ext import redis_proxy

from ticketmaster.redis_cache.repositories import NamespaceRepository


async def rotate_service_redis_cache_namespace() -> str:
    return await NamespaceRepository.set(redis=redis_proxy.redis)
