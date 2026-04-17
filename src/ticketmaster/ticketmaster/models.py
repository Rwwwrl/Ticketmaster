from datetime import datetime

from libs.sqlmodel_ext import BaseSqlModel
from sqlalchemy import Column, DateTime, Identity, Integer, PrimaryKeyConstraint, String
from sqlmodel import Field

from ticketmaster.enums import EventTypeEnum, TicketStatusEnum


class Event(BaseSqlModel, table=True):
    __tablename__ = "event"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
    name: str
    description: str
    type: EventTypeEnum = Field(sa_type=String)
    start_at: datetime = Field(sa_type=DateTime(timezone=True))


class User(BaseSqlModel, table=True):
    __tablename__ = "user"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))


class Ticket(BaseSqlModel, table=True):
    __tablename__ = "ticket"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
    event_id: int = Field(foreign_key="event.id")
    user_id: int | None = Field(foreign_key="user.id")
    status: TicketStatusEnum = Field(sa_type=String)
    reserved_at: datetime | None = Field(sa_type=DateTime(timezone=True))
    booked_at: datetime | None = Field(sa_type=DateTime(timezone=True))
