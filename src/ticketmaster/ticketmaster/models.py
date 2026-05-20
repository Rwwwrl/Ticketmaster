from datetime import datetime
from uuid import UUID

from libs.sqlmodel_ext import BaseSqlModel, EnumString
from sqlalchemy import Column, Computed, DateTime, Identity, Index, Integer, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field

from ticketmaster.enums import EventTypeEnum, TicketStatusEnum


class Event(BaseSqlModel, table=True):
    __tablename__ = "event"
    __table_args__ = (
        PrimaryKeyConstraint("id"),
        Index("ix_event_start_at_id", "start_at", "id"),
        Index("ix_event_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
    name: str
    description: str
    type: EventTypeEnum = Field(sa_type=EnumString(EventTypeEnum))
    start_at: datetime = Field(sa_type=DateTime(timezone=True))

    # NOTE @sosov: Postgres-managed generated tsvector for full-text search; Python never
    # writes to it.
    search_vector: str | None = Field(
        default=None,
        sa_column=Column(
            TSVECTOR,
            Computed(
                "setweight(to_tsvector('english', coalesce(name, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(description, '')), 'B')",
                persisted=True,
            ),
        ),
    )


class User(BaseSqlModel, table=True):
    __tablename__ = "user"
    __table_args__ = (
        PrimaryKeyConstraint("id"),
        Index("ix_user_uuid", "uuid", unique=True),
        Index("ix_user_email", "email", unique=True),
        Index("ix_user_pool_external_id", "pool_id", "external_id", unique=True),
    )

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
    uuid: UUID
    pool_id: str
    email: str
    external_id: str


class Ticket(BaseSqlModel, table=True):
    __tablename__ = "ticket"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
    event_id: int = Field(foreign_key="event.id")
    user_id: int | None = Field(foreign_key="user.id")
    status: TicketStatusEnum = Field(sa_type=EnumString(TicketStatusEnum))
    reserved_at: datetime | None = Field(sa_type=DateTime(timezone=True))
    booked_at: datetime | None = Field(sa_type=DateTime(timezone=True))
