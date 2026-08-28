---
name: testing
description: Apply Ticketmaster's pytest testing conventions. Use when adding or reviewing tests, choosing test boundaries, creating fixtures or factories, testing FastAPI, SQLModel, Redis, AWS or Lambda behavior, mocking external dependencies, diagnosing failures, or running coverage and CI checks.
---

# Ticketmaster Testing

Test observable behavior at the lowest boundary that proves the requirement. Prefer real project infrastructure for persistence and cache behavior; isolate external systems.

## Place and Name Tests

Mirror source structure inside each package:

- `src/libs/libs/tests/`
- `src/ticketmaster/ticketmaster/tests/`
- `src/lambdas/cognito_pre_signup/tests/`

Name files `test_<module>.py`. Name tests after behavior, usually:

```text
test_<subject>_when_<condition>_<outcome>
```

Keep test names specific enough that a failure explains the broken contract. Use parametrization when inputs change but behavior is the same.

The root pytest configuration uses `--import-mode=importlib`. Do not add `__init__.py` files to the libs or Ticketmaster test trees. Preserve the Lambda test package's existing structure.

## Follow Core Conventions

- Run pytest through Poetry from the repository root.
- Annotate every test and fixture return type.
- Use keyword arguments in calls.
- Mark every async test with `@pytest.mark.asyncio(loop_scope="session")`.
- Define async fixtures with `pytest_asyncio.fixture`, not `pytest.fixture`.
- Use session scope for shared expensive fixtures such as the app, client, database engine, and Redis client. Use function scope for test-specific data, dependency overrides, or cleanup.
- Arrange setup, action, and assertions clearly without explanatory comments for obvious operations.
- Test one coherent behavior per test.
- Assert exact status, typed payload, persisted state, cache state, exception, or external call as appropriate.

## Choose the Test Boundary

- Call pure functions, serializers, cursor logic, and FastAPI dependencies directly.
- Test repositories and business services against real PostgreSQL.
- Test cache repositories and cache-aside services against real Redis.
- Test HTTP contracts through the in-process FastAPI client.
- Build a minimal FastAPI app inside middleware tests so unrelated application setup does not affect them.
- Call Lambda handlers directly and isolate AWS and outbound HTTP boundaries.

Do not mock an internal repository merely to make an endpoint test easy when the real database fixture can prove the complete behavior.

## Test PostgreSQL Behavior

The `libs.tests_ext.sqlmodel_fixtures` plugin:

- Recreates a dedicated `test` database for the session.
- Binds the global `Session`.
- Creates tables from `BaseSqlModel.metadata`.
- Truncates declared tables after each database-using test.

The Ticketmaster test conftest provides `settings`, `autocleared_sqlmodel_tables`, `fastapi_app`, and `async_client`. Add every new model to `autocleared_sqlmodel_tables`; list dependent tables before their parents.

Build models with factories from `ticketmaster/tests/factories.py` and persist them with:

```python
from libs.tests_ext.factories import insert

event = EventFactory()
await insert(event)
```

The helper flushes, refreshes, and expunges inserted models. For post-action assertions, open `Session()` directly and query the database. Test constraints at the database boundary in addition to HTTP validation.

## Test Redis Behavior

The `libs.tests_ext.redis_fixtures` plugin configures `redis_proxy` with Redis database 15 and flushes it before the suite, after each Redis-using test, and after the suite.

Use the real `redis` fixture for round trips, key isolation, TTLs, invalidation, malformed documents, and cache-aside behavior. Monkeypatch Redis methods only to simulate failures that a real healthy server cannot produce deterministically. Assert that Redis failures fall through to the authoritative data source where required.

## Test FastAPI Contracts

Use the shared `AsyncClient` with `ASGITransport`. The shared test app registers public and admin routers directly; it does not run the production lifespan or middleware stack.

For endpoint changes, cover:

- Success status and response schema.
- Required-field and value validation.
- Authentication and authorization behavior.
- Domain-exception to HTTP-status mapping.
- Database, cache, or external side effects.
- Ordering, pagination, and boundary conditions when relevant.

Parse response JSON into the declared Pydantic response schema before field assertions:

```python
response = await async_client.get(url="/api/v1/events/1")

assert response.status_code == 200
body = EventResponseSchema(**response.json())
assert body.id == 1
```

Override FastAPI dependencies through `fastapi_app.dependency_overrides` and always clear overrides after `yield`.

## Isolate External Boundaries

Use `respx` for outbound HTTP, `monkeypatch` for module attributes and failure injection, and `AsyncMock` or `MagicMock` for AWS clients and context managers. Patch where the code looks up the dependency, not where it was originally defined.

Read [references/mocking.md](references/mocking.md) whenever a test needs mocks, dependency overrides, AWS stubs, or outbound HTTP interception.

## Run Tests

Start PostgreSQL and Redis for integration tests:

```bash
just up-infra
```

Run the narrowest relevant test first:

```bash
poetry run pytest path/to/test_file.py -s
poetry run pytest path/to/test_file.py::test_name -s
```

Run the complete suite with `just test` or the CI-equivalent command:

```bash
poetry run pytest --cov=src/libs/libs --cov=src/ticketmaster/ticketmaster --cov-report=term-missing --cov-fail-under=75
```

Then run:

```bash
poetry run ruff check .
poetry run ruff format --check .
```

If a new required setting is introduced, add an explicit test value to the root pytest `env` list. Changes anywhere under `src/libs/` or `src/ticketmaster/`, including tests, require the corresponding package version bump because PR validation is path-based.
