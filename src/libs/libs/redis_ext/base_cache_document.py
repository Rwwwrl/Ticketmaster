from typing import ClassVar, Self

from pydantic import BaseModel, ValidationError

from libs.redis_ext.exceptions import FromRawCacheValidationError


class BaseCacheDocument(BaseModel):
    """Base class for typed documents persisted in Redis."""

    # NOTE @sosov: Cache keys must embed this version (e.g. "event:v1:<id>"). Bump it on every
    # schema change so old- and new-format documents live under disjoint keys during rolling
    # deploys; the previous generation expires via TTL.
    version: ClassVar[int]

    @classmethod
    def from_raw_cache(cls, raw: str | bytes) -> Self:
        try:
            return cls.model_validate_json(raw)
        except ValidationError as exc:
            raise FromRawCacheValidationError(f"Failed to deserialize {cls.__name__}") from exc
