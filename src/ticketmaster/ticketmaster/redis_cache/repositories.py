from uuid import uuid4

from libs.redis_ext.cache import FromRawCacheValidationError, ServiceCacheNotFoundException
from redis.asyncio import Redis

from ticketmaster.enums import EventSortKeyEnum
from ticketmaster.exceptions import EventCacheDocumentNotFoundException
from ticketmaster.redis_cache import consts
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.redis_cache.service_caches import ListEventsPageServiceCache
from ticketmaster.schemas.dtos import BaseEventDTO


class EventCacheRepository:
    @classmethod
    def _cache_key(cls, event_id: int, version: int) -> str:
        return f"event:v{version}:{event_id}"

    @classmethod
    async def get_by_id(cls, redis: Redis, _id: int) -> BaseEventDTO:
        raw = await redis.get(name=cls._cache_key(event_id=_id, version=EventCacheDocument.version))
        if raw is None:
            raise EventCacheDocumentNotFoundException(f"Event cache document not found for id={_id}")

        cache_document = EventCacheDocument.from_raw_cache(raw)
        return BaseEventDTO.from_cache_document(document=cache_document)

    @classmethod
    async def set(cls, redis: Redis, dto: BaseEventDTO, ttl_seconds: int = consts.EVENT_CACHE_TTL_SECONDS) -> None:
        cache_document = EventCacheDocument.from_dto(dto=dto)
        await redis.set(
            name=cls._cache_key(event_id=cache_document.id, version=EventCacheDocument.version),
            value=cache_document.model_dump_json(),
            ex=ttl_seconds,
        )

    @classmethod
    async def get_many_by_ids(cls, redis: Redis, ids: list[int]) -> list[BaseEventDTO]:
        if not ids:
            return []

        keys = [cls._cache_key(event_id=event_id, version=EventCacheDocument.version) for event_id in ids]

        raw_documents = await redis.mget(keys=keys)

        documents: list[BaseEventDTO] = []
        for raw in raw_documents:
            if raw is None:
                continue

            try:
                cache_document = EventCacheDocument.from_raw_cache(raw)
            except FromRawCacheValidationError:
                continue

            documents.append(BaseEventDTO.from_cache_document(document=cache_document))

        return documents

    @classmethod
    async def set_many(
        cls,
        redis: Redis,
        dtos: list[BaseEventDTO],
        ttl_seconds: int = consts.EVENT_CACHE_TTL_SECONDS,
    ) -> None:
        if not dtos:
            return

        async with redis.pipeline(transaction=False) as pipe:
            for dto in dtos:
                cache_document = EventCacheDocument.from_dto(dto=dto)
                pipe.set(
                    name=cls._cache_key(event_id=cache_document.id, version=EventCacheDocument.version),
                    value=cache_document.model_dump_json(),
                    ex=ttl_seconds,
                )
            await pipe.execute()


class NamespaceRepository:
    @classmethod
    def _cache_key(cls) -> str:
        return "namespace"

    @classmethod
    async def get(cls, redis: Redis) -> str:
        raw = await redis.get(name=cls._cache_key())
        return raw.decode()

    @classmethod
    async def set(cls, redis: Redis) -> str:
        namespace = str(uuid4())
        await redis.set(name=cls._cache_key(), value=namespace)
        return namespace


class ListEventsPageServiceCacheRepository:
    @classmethod
    def cache_key(
        cls,
        service_name: str,
        version: str,
        namespace: str,
        cursor: str | None,
        sort_key: EventSortKeyEnum,
        page_size: int,
    ) -> str:
        return (
            f"service={service_name}:v={version}:namespace={namespace}:cursor={cursor}:"
            f"sort_key={sort_key.value}:page_size={page_size}"
        )

    @classmethod
    async def get(
        cls,
        redis: Redis,
        key: str,
    ) -> ListEventsPageServiceCache:
        raw = await redis.get(name=key)

        if raw is None:
            raise ServiceCacheNotFoundException(f"Service cache not found for key={key}")

        return ListEventsPageServiceCache.from_raw_cache(raw=raw)

    @classmethod
    async def set(
        cls,
        redis: Redis,
        key: str,
        value: ListEventsPageServiceCache,
        ttl_seconds: int = consts.SERVICE_CACHE_TTL_SECONDS,
    ) -> None:
        await redis.set(
            name=key,
            value=value.model_dump_json(),
            ex=ttl_seconds,
        )
