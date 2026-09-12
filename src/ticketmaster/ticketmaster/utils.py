from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from ticketmaster.models import Event
    from ticketmaster.schemas.dtos import BaseEventDTO


def event_validate[T: BaseEventDTO | Event](_self: T) -> T:
    if (_self.trailer_bucket is None) != (_self.trailer_key is None):
        raise ValueError("trailer_bucket and trailer_key must both be set or both be None")

    return _self


def init_sqlmodel_engine(db_url: str) -> AsyncEngine:
    return create_async_engine(
        url=db_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args={"command_timeout": 15},
    )
