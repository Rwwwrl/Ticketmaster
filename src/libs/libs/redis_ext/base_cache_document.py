from pydantic import BaseModel


class BaseCacheDocument(BaseModel):
    """Base class for typed documents persisted in Redis."""
