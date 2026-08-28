from libs.sqlmodel_ext import BaseSqlModel
from sqlalchemy import Column, Identity, Integer, PrimaryKeyConstraint
from sqlmodel import Field


class Visit(BaseSqlModel, table=True):
    __tablename__ = "visit"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
