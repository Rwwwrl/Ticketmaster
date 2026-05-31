from redis.asyncio import Redis

from ticketmaster.exceptions import EventCacheDocumentNotFoundException
from ticketmaster.redis_cache.cache_documents import EventCacheDocument
from ticketmaster.schemas.dtos import BaseEventDTO

_EVENT_TTL_SECONDS = 300


class EventCacheRepository:
    @classmethod
    def _event_key(cls, event_id: int) -> str:
        return f"event:{event_id}"

    @classmethod
    async def get_by_id(cls, redis: Redis, _id: int) -> BaseEventDTO:
        raw = await redis.get(name=cls._event_key(event_id=_id))
        if raw is None:
            raise EventCacheDocumentNotFoundException(f"Event cache document not found for id={_id}")

        cache_document = EventCacheDocument.model_validate_json(raw)
        return BaseEventDTO.from_cache_document(document=cache_document)

    @classmethod
    async def set(cls, redis: Redis, dto: BaseEventDTO, ttl_seconds: int = _EVENT_TTL_SECONDS) -> None:
        cache_document = EventCacheDocument.from_dto(dto=dto)
        await redis.set(
            name=cls._event_key(event_id=cache_document.id),
            value=cache_document.model_dump_json(),
            ex=ttl_seconds,
        )

    @classmethod
    async def get_many_by_ids(cls, redis: Redis, ids: list[int]) -> list[BaseEventDTO]:
        if not ids:
            return []

        keys = [cls._event_key(event_id=event_id) for event_id in ids]

        raw_documents = await redis.mget(keys=keys)

        documents: list[BaseEventDTO] = []
        for raw in raw_documents:
            if raw is None:
                continue

            cache_document = EventCacheDocument.model_validate_json(raw)
            documents.append(BaseEventDTO.from_cache_document(document=cache_document))

        return documents

    @classmethod
    async def set_many(cls, redis: Redis, dtos: list[BaseEventDTO], ttl_seconds: int = _EVENT_TTL_SECONDS) -> None:
        if not dtos:
            return

        async with redis.pipeline(transaction=False) as pipe:
            for dto in dtos:
                cache_document = EventCacheDocument.from_dto(dto=dto)
                pipe.set(
                    name=cls._event_key(event_id=cache_document.id),
                    value=cache_document.model_dump_json(),
                    ex=ttl_seconds,
                )
            await pipe.execute()
