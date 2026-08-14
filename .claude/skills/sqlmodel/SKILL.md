---
name: sqlmodel
description: Apply Ticketmaster's SQLModel-first database conventions. Use for models, fields, constraints, indexes, sessions, repositories, queries, transactions, DTO mappings, Alembic migrations, database fixtures, and persistence tests.
---

# Ticketmaster SQLModel

Prefer SQLModel's typed surface for domain persistence and use SQLAlchemy only for constructs SQLModel does not expose.

## Use SQLModel First

Prefer:

```python
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

result = await session.exec(select(Event))
events = result.all()
```

Use SQLAlchemy for engine/session-factory wiring, raw `text()`, DML expressions, explicit `Column` definitions, constraints, indexes, PostgreSQL-specific types, and Alembic operations. Use `session.execute(text(...))` for raw SQL; use `session.exec(...)` for SQLModel selects and repository DML.

The canonical factory is `libs.sqlmodel_ext.Session`, configured as:

```python
Session = async_sessionmaker(class_=AsyncSession, autobegin=False)
```

Always open an explicit `session.begin()` transaction at the route or entrypoint boundary. Pass the session downward. Never commit in a service or repository.

## Define Models

- Keep service models flat in `src/ticketmaster/ticketmaster/models.py`.
- Inherit `libs.sqlmodel_ext.BaseSqlModel` and set `table=True`.
- Use `Field` for model fields and foreign keys.
- Keep fields required unless nullability is part of the real lifecycle.
- Use timezone-aware `DateTime(timezone=True)`.
- Use `Decimal` with explicit `Numeric(precision=..., scale=...)`.
- Persist enums with `Field(sa_type=EnumString(MyEnum))`; enum class names end in `Enum`.
- Declare indexes and constraints explicitly when query behavior or uniqueness depends on them.

Use the existing identity pattern:

```python
class Event(BaseSqlModel, table=True):
    __tablename__ = "event"
    __table_args__ = (PrimaryKeyConstraint("id"),)

    id: int | None = Field(default=None, sa_column=Column(Integer, Identity()))
```

The optional identity field reflects the pre-insert lifecycle; do not make ordinary required columns optional for convenience.

`BaseSqlModel` supplies timezone-aware `created_at` and `updated_at`. ORM updates trigger the timestamp listener. SQLAlchemy bulk `update()` bypasses it, so set `updated_at=utc_now()` explicitly in bulk DML.

## Implement Repositories

- Use async class methods that accept `AsyncSession` by keyword.
- Return frozen DTOs, not ORM models.
- Map explicitly with `BaseEventDTO.from_sqlmodel(model=event)`.
- On create, call `session.add`, `await session.flush()`, and `await session.refresh(model)` before mapping.
- Raise domain exceptions derived from `libs.sqlmodel_ext.NotFoundException` for missing rows. Translate them only at the HTTP boundary.
- Use stable, explicit ordering for pagination.
- Avoid read-then-write for contested state. Use one conditional `UPDATE` and check `rowcount == 1`, following ticket reservation and booking.

When a model changes, update every affected DTO, serializer, response schema, cache document, factory, and test.

## Create Migrations

Every schema change requires an Alembic revision under:

- `migrations/versions/expand/` for additive or backward-compatible changes
- `migrations/versions/contract/` for destructive cleanup after compatible code is deployed

Generate from the service context:

```bash
poetry -C src/ticketmaster run alembic revision --autogenerate -m "<message>" --head expand@head --version-path migrations/versions/expand
```

Use the corresponding `contract@head` and contract directory for contract changes. Autogeneration requires a reachable configured database.

Review the generated operations manually. Metadata-based tests do not prove the migration works. Keep `ticketmaster.models` imported in `migrations/env.py`. Existing downgrades are intentionally no-op; do not invent a destructive rollback without an explicit project decision.

Production applies `expand@head` before the rollout and `contract@head` only after the new service is healthy. Preserve that order and design migrations for mixed old/new pods. (The pipeline has no migration step while the backend is between ECS and Kubernetes; the rule stands for when it returns.)

## Test Persistence

Start infrastructure when needed:

```bash
just up-infra
```

The shared fixture creates schema from `BaseSqlModel.metadata`, binds the global `Session`, and truncates declared tables between tests. Add every new table to `autocleared_sqlmodel_tables` in the service test configuration.

Use factories and `libs.tests_ext.factories.insert(...)`. Test constraints, mapping, not-found behavior, ordering, pagination boundaries, and atomic concurrency conditions. Also validate the Alembic heads and migration against a local database:

```bash
poetry -C src/ticketmaster run alembic heads
poetry run pytest path/to/database_tests.py -s
poetry run ruff check .
poetry run ruff format --check .
```

Bump the affected `src/libs` or `src/ticketmaster` package version for source changes; pull-request CI requires it.
