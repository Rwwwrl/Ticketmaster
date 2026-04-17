---
name: testing
description: Guides pytest test writing for ticketmaster. Covers async test patterns, httpx client fixtures, conftest structure, and mock patterns. Use when writing tests, creating fixtures, debugging test failures, or setting up test infrastructure. Trigger phrases include "write test", "pytest", "mock", "test case", "fixture", "conftest", "integration test".
user_invocable: true
---

# Testing

## Test Example

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_readiness_check_when_db_reachable(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/readiness_check")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

## Test Naming

```
test_<function_name>_when_<condition>
```

Examples: `test_readiness_check_when_db_unreachable`, `test_request_id_middleware_when_overly_long_id`.

## File Structure

Tests mirror source structure: for every `pkg/foo/bar.py` there is a `pkg/tests/foo/test_bar.py`. `tests/` lives **inside** the Python package (next to the source modules), not alongside it. No `__init__.py` files — tests run under `--import-mode=importlib`.

Run from the project root: `poetry run pytest`.

## Async Configuration

- `asyncio_default_fixture_loop_scope = "session"` in pytest config
- `@pytest.mark.asyncio(loop_scope="session")` on every async test — no exceptions
- `@pytest_asyncio.fixture(scope="session")` for async fixtures (not `@pytest.fixture`)
- `--import-mode=importlib` — no `__init__.py` in test dirs

## Conftest Patterns

Two patterns depending on what the tests touch:

- **Self-contained inline fixtures.** Middleware and other unit-style tests build a minimal `FastAPI` app and `async_client` directly inside the test file. There is no shared conftest for `libs` tests.
- **Service conftest with DB.** Tests that exercise the service against Postgres share a `conftest.py` at the service tests root. It supplies `settings`, `autocleared_sqlmodel_tables`, `fastapi_app`, and `async_client`.

## DB Test Infrastructure

For tests that touch Postgres, the shared plugin `libs.tests_ext.sqlmodel_fixtures` (loaded via `-p` in the root `pyproject.toml`) provides:

- `sqlmodel_engine` (session scope) — creates/drops a dedicated `test` database and runs `create_all`.
- `_clear_sqlmodel_tables` (autouse) — `TRUNCATE`s tables after each test.

The service conftest must provide:

- `settings` (session) — a `PostgresSettingsMixin` instance.
- `autocleared_sqlmodel_tables` (session) — `list[type[BaseSqlModel]]` for the plugin to truncate. List child tables before parents so `TRUNCATE ... CASCADE` is predictable.
- `fastapi_app` (session) — a **test-only** `FastAPI` instance with just the routers under test. Do not import the prod `app` — its lifespan runs at import time and couples tests to the full middleware stack.

Postgres must be up (`just up-infra`) before running DB tests.

## Response Validation

Validate responses with Pydantic schemas, not raw dicts:

```python
response = await async_client.get(url="/v1/events/")
assert response.status_code == 200
content = EventListResponseSchema(**response.json())
```

## Mock Patterns

See [references/mocks.md](references/mocks.md) for `patch`, `AsyncMock`, `side_effect`, parenthesized multi-patch, and argument assertions.

## What's Convenient

- `httpx.AsyncClient` + `ASGITransport` hits the app in-process — no network, no server.
- Session-scoped fixtures build the app/client once per suite, so the cost is paid upfront.
- The DB plugin handles the full `test` database lifecycle and per-test cleanup; service conftest only declares which tables to wipe.
- `caplog` works for log-based assertions without extra setup.
- DB assertions can open `Session()` directly — no need to round-trip through the API.

## Conventions

| Rule              | Detail                                                         |
| ----------------- | -------------------------------------------------------------- |
| Return types      | Always annotate (`-> None`, `-> AsyncGenerator[AsyncClient]`)  |
| Keyword args      | Always use (`url=`, `json=`, `headers=`, `router=`)            |
| Internal fixtures | Prefix with `_` (e.g. `_clear_sqlmodel_tables`)                |
| Line length       | E501 ignored under `**/tests/**/*` (root `pyproject.toml`)     |
| DB assertions     | Open `Session()` directly, don't go through the API            |
| Fixture scope     | Session for everything except function-scoped cleanup fixtures |
| Test marker       | `@pytest.mark.asyncio(loop_scope="session")` always            |
| No `__init__.py`  | Tests run under `--import-mode=importlib`                      |
