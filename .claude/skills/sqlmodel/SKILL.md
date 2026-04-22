---
name: sqlmodel
description: Encodes the SQLModel-first principle for ticketmaster. Prefer sqlmodel imports (SQLModel, Field, select, AsyncSession from sqlmodel.ext.asyncio.session) over their sqlalchemy equivalents; fall back to sqlalchemy only when SQLModel does not provide the construct (text(), async_sessionmaker, create_async_engine, dialect-specific types). Use whenever writing models, repositories, sessions, queries, migrations, or any DB-touching code — even if the user does not say "sqlmodel" explicitly. Trigger phrases include "sqlmodel", "AsyncSession", "session", "select", "query", "repository", "model", "ORM", "table", "Field", "engine", "execute", "exec".
user_invocable: true
---

# SQLModel

## SQLModel-First Principle

**Always reach for the sqlmodel import first.** Drop down to sqlalchemy only when SQLModel does not expose what you need. Two reasons this matters here:

1. `sqlmodel.select` + `AsyncSession.exec()` carry the model type through the call, so you get `Result[Event]` instead of `Result[Row[tuple[Event]]]`. Type checkers and IDEs see the model directly, and you skip the `.scalars()` unwrap.
2. Mixing both libraries in repositories blurs which layer owns what. A consistent SQLModel surface keeps domain code uniform; sqlalchemy stays the implementation detail it should be.

## Import Cheat Sheet

Prefer the left column. Reach for the right column only for the listed fallback cases.

| Use this (SQLModel)                                          | Instead of (sqlalchemy)                                |
| ------------------------------------------------------------ | ------------------------------------------------------ |
| `from sqlmodel import SQLModel, Field`                       | `from sqlalchemy.orm import declarative_base`, `Column` |
| `from sqlmodel import select`                                | `from sqlalchemy import select`                        |
| `from sqlmodel.ext.asyncio.session import AsyncSession`      | `from sqlalchemy.ext.asyncio import AsyncSession`      |
| `await session.exec(select(Event))` then `result.all()`      | `await session.execute(...)` then `.scalars().all()`   |
| `Field(foreign_key="event.id")`                              | `Column(..., ForeignKey("event.id"))`                  |

## When sqlalchemy is the Right Import

SQLModel intentionally does not wrap these. Use sqlalchemy directly:

- `text()` for raw SQL — `session.execute(text("SELECT 1"))`. Use `.execute()` here, not `.exec()` (`.exec()` is sqlmodel-typed-only).
- `async_sessionmaker` for the session factory — pass `class_=AsyncSession` from sqlmodel so produced sessions are sqlmodel's typed subclass.
- `create_async_engine`, `make_url`, `AsyncEngine` for engine wiring.
- Dialect-specific column types not surfaced by SQLModel (e.g. `postgresql.JSONB`, `ARRAY`).
- Migration ops (`op.create_table`, `sa.Column`) inside Alembic revision files.

## Session Factory

`src/libs/libs/sqlmodel_ext/session.py` binds sqlmodel's `AsyncSession` to sqlalchemy's `async_sessionmaker`. This is the canonical pattern:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

Session = async_sessionmaker(class_=AsyncSession, autobegin=False)
```

`Session()` produced from this factory is a sqlmodel `AsyncSession` — `.exec()` and `.execute()` both work, and result types stay typed.

Routes open a session per request and pair it with an explicit transaction:

```python
async with Session() as session, session.begin():
    events = await EventRepository.get_all(session=session)
```

## Repository Pattern

Repositories take `AsyncSession` from `sqlmodel.ext.asyncio.session` and return DTOs (never models — see the auto-memory note on this). Use `session.exec(select(...))` and call `.all()` / `.first()` / `.one()` directly:

```python
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from ticketmaster.models import Event
from ticketmaster.schemas.dtos import EventDTO


class EventRepository:
    @classmethod
    async def get_all(cls, session: AsyncSession) -> list[EventDTO]:
        result = await session.exec(select(Event))
        return [EventDTO.from_sqlmodel(event) for event in result.all()]
```

No `.scalars()`. No tuple unpacking. The model class flows through.

### Method naming

Prefer `get_one`, `get_all`, `get_by_<field>` over `list_*` / `find_*`. The paginated form is `get_all_paginated` — same prefix, same mental model, just returns `(list[DTO], total)`:

```python
from sqlalchemy import func
from sqlmodel import select

class EventRepository:
    @classmethod
    async def get_all_paginated(
        cls,
        session: AsyncSession,
        page: int,
        page_size: int,
    ) -> tuple[list[EventDTO], int]:
        offset = (page - 1) * page_size
        items_result = await session.exec(
            select(Event).order_by(Event.start_at, Event.id).offset(offset).limit(page_size)
        )
        items = [EventDTO.from_sqlmodel(model=event) for event in items_result.all()]

        # Count the PK column, not `*` / `select_from(...)`. `func.count(Event.id)` keeps
        # the scalar return type obvious — `.one()` gives you a plain int.
        total_result = await session.exec(select(func.count(Event.id)))
        total = total_result.one()

        return items, total
```

## Models

Inherit from `BaseSqlModel` (from `libs.sqlmodel_ext`) — a `SQLModel` subclass that wires the `updated_at` listener and is the metadata target Alembic autogenerates against. Declare columns with sqlmodel's `Field`; foreign keys go through `Field(foreign_key="other_table.id")`, not `sqlalchemy.ForeignKey`. Reach for `sa_type=` only when you need a custom column type that SQLModel can't infer from the Python annotation:

```python
from libs.sqlmodel_ext import BaseSqlModel, EnumString
from sqlmodel import Field

from ticketmaster.enums import EventTypeEnum


class Event(BaseSqlModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str
    type: EventTypeEnum = Field(sa_type=EnumString(EventTypeEnum))
    start_at: datetime
```

## Common Pitfalls

- **Importing `select` from sqlalchemy in a repository.** Loses typed results; means you also have to `.scalars()` unwrap. Switch to `from sqlmodel import select` and `session.exec(...)`.
- **Typing a session parameter as sqlalchemy's `AsyncSession`.** Callers lose `.exec()` in IDE hints and may default to `.execute()`. Type as `sqlmodel.ext.asyncio.session.AsyncSession`.
- **Building the session factory without `class_=AsyncSession`.** Sessions come back as plain sqlalchemy `AsyncSession` — `.exec()` won't exist on them. Always pass `class_=AsyncSession` from sqlmodel.
- **Using `.exec()` with `text()`.** `.exec()` is for sqlmodel-typed selects only. Raw `text()` queries go through `.execute()`.
