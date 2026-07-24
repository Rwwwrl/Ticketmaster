from typing import Self

from pydantic import ValidationError

from libs.common.schemas.dto import DTO
from libs.redis_ext.cache.exceptions import FromRawCacheValidationError


class BaseServiceCache(DTO):
    """Base class for typed service results persisted in Redis."""

    @classmethod
    def from_raw_cache(cls, raw: str | bytes) -> Self:
        try:
            return cls.model_validate_json(raw)
        except ValidationError as exc:
            raise FromRawCacheValidationError(f"Failed to deserialize {cls.__name__}") from exc
