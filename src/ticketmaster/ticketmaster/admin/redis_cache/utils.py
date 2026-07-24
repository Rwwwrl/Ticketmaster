from libs.redis_ext import redis_proxy

from ticketmaster.admin.redis_cache.repositories import AdminEventCacheRepository
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.repositories import NamespaceRepository


async def rotate_service_cache_namespace() -> str:
    return await NamespaceRepository.set(redis=redis_proxy.redis)


async def invalidate_event_cache_document_by_id(_id: int) -> None:
    # NOTE @sosov: During a rolling deploy only adjacent schema versions have live readers,
    # and versions advance by exactly 1 per deploy — so N-1/N/N+1 covers both directions of
    # the deploy race, including old code invalidating the new generation's key. Residual:
    # a single deploy carrying two version bumps puts new pods at N+2, out of reach — that
    # entry stays stale until TTL.
    current_version = EventCacheDocument.version
    for version in (current_version - 1, current_version, current_version + 1):
        await AdminEventCacheRepository.delete_by_id(redis=redis_proxy.redis, _id=_id, version=version)
