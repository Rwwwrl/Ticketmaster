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

The `tests/` directory lives **inside** the Python package (next to the source modules), not alongside it. Tests mirror source structure — for every `pkg/foo/bar.py` there is a `pkg/tests/foo/test_bar.py`. No `__init__.py` files (importlib mode).

```
src/libs/
└── libs/
    ├── fastapi_ext/
    │   └── middlewares/
    │       ├── request_id.py
    │       └── security_headers.py
    └── tests/
        └── fastapi_ext/
            └── middlewares/
                ├── test_request_id.py
                └── test_security_headers.py

src/ticketmaster/
└── ticketmaster/
    ├── http/
    │   └── main.py
    ├── models.py
    └── tests/
        ├── conftest.py
        └── http/
            └── test_main.py
```

Both test roots are registered from the workspace root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_default_fixture_loop_scope = "session"
addopts = "--import-mode=importlib"
testpaths = ["src/libs/libs/tests", "src/ticketmaster/ticketmaster/tests"]
```

When running pytest from inside a single package (e.g. `cd src/ticketmaster && poetry run pytest`), that package's own `pyproject.toml` points at its local `ticketmaster/tests`.

Run from the project root: `poetry run pytest`.

## Async Configuration

- `asyncio_default_fixture_loop_scope = "session"` in pytest config
- `@pytest.mark.asyncio(loop_scope="session")` on every async test — no exceptions
- `@pytest_asyncio.fixture(scope="session")` for async fixtures (not `@pytest.fixture`)
- `--import-mode=importlib` — no `__init__.py` in test dirs

## conftest Patterns

### Self-contained test file (libs pattern)

For middleware / unit tests with no shared conftest, define fixtures inline. This is the style used by the existing `src/libs/tests/test_*_middleware.py` files.

```python
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from libs.fastapi_ext.middlewares import SecurityHeadersMiddleware


@pytest.fixture(scope="session")
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware)

    router = APIRouter()

    @router.get("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    test_app.include_router(router=router)
    return test_app


@pytest_asyncio.fixture(scope="session")
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio(loop_scope="session")
async def test_security_headers_when_success_adds_nosniff(async_client: AsyncClient) -> None:
    response = await async_client.get(url="/test")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
```

### DB integration conftest (service app)

Tests that touch Postgres must run against a **dedicated throwaway database**, not `postgres_db_url`'s target — otherwise they'd mutate dev data. The reusable `sqlmodel_engine` fixture lives in the shared plugin `libs.tests_ext.sqlmodel_fixtures`, loaded from the root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib -p libs.tests_ext.sqlmodel_fixtures"
```

The plugin (`src/libs/libs/tests_ext/sqlmodel_fixtures.py`) does the full life cycle per session:

1. Connects to the `postgres` admin database, runs `DROP DATABASE IF EXISTS test` + `CREATE DATABASE test`.
2. Builds an engine against the fresh `test` DB, wires `Session.configure(bind=engine)`.
3. Runs `BaseSqlModel.metadata.create_all` to build the schema.
4. Yields the engine.
5. On teardown: disposes the engine, reconnects as admin, `DROP DATABASE test`.

It also ships an autouse `_clear_sqlmodel_tables` fixture that TRUNCATEs the service's tables after each test when the service provides an `autocleared_sqlmodel_tables` fixture.

The service conftest supplies three session-scoped fixtures: `settings` (any `PostgresSettingsMixin`) and `autocleared_sqlmodel_tables` (the tables to wipe between tests) are consumed by the plugin; `fastapi_app` builds a **test-only FastAPI instance** that includes just the routers under test. Do **not** import the real `app` from `ticketmaster.http.main` into tests — the prod app runs its lifespan at import time, couples tests to the full middleware stack, and hits the real DB URL.

The conftest also imports the service's models module so `BaseSqlModel.metadata` is populated before `create_all` runs. See `src/ticketmaster/ticketmaster/tests/conftest.py`:

```python
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from libs.sqlmodel_ext import BaseSqlModel
from sqlalchemy.ext.asyncio import AsyncEngine

from ticketmaster.http.v1 import v1_router
from ticketmaster.models import Event, Ticket, User
from ticketmaster.settings import Settings
from ticketmaster.settings import settings as ticketmaster_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return ticketmaster_settings


@pytest.fixture(scope="session")
def autocleared_sqlmodel_tables() -> list[type[BaseSqlModel]]:
    return [Ticket, User, Event]


@pytest_asyncio.fixture(scope="session")
async def fastapi_app(sqlmodel_engine: AsyncEngine) -> AsyncGenerator[FastAPI]:
    app = FastAPI()
    app.state.sqlmodel_engine = sqlmodel_engine
    app.include_router(router=v1_router, prefix="/v1")
    yield app


@pytest_asyncio.fixture(scope="session")
async def async_client(fastapi_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
```

Notes:
- `httpx.ASGITransport` does **not** run the app's lifespan. `Session.configure(bind=engine)` inside the plugin replaces what `http/main.py::lifespan` does for the DB; the `fastapi_app` fixture attaches the engine to `app.state` the same way the real lifespan does.
- `/health` and `/readiness_check` live on the prod app in `http/main.py` and are deliberately not included in the test app — they're trivial liveness probes, not business logic.
- Postgres must be up (`just up-infra`) — the plugin talks to the real server and creates/drops the `test` database.
- `_clear_sqlmodel_tables` quotes table names so reserved words like `"user"` work.
- Ordering inside `autocleared_sqlmodel_tables` matters for FK dependencies: list child tables before their parents so TRUNCATE CASCADE behaves predictably.

## Response Validation

Use Pydantic schemas to validate responses, not raw dicts:

```python
response = await async_client.get(url="/v1/events/")
assert response.status_code == 200
content = EventListResponseSchema(**response.json())
```

## Mock Patterns

Full recipes in [references/mocks.md](references/mocks.md). Quick summary:

- Configure mocks in the `patch()` call — never mutate them after creation.
- Use `new_callable=AsyncMock` for async targets.
- Multiple patches: parenthesized `with (patch(...), patch(...)):`.
- Assert with `.assert_called_once()` + `.call_args.kwargs[...]`.

## Conventions

| Rule | Detail |
|------|--------|
| Return types | Always annotate (`-> None`, `-> AsyncGenerator[AsyncClient]`) |
| Keyword args | Always use (`url=`, `json=`, `headers=`, `router=`) |
| Internal fixtures | Prefix with `_` (e.g. `_clear_sqlmodel_tables`) |
| Line length | E501 ignored under `**/tests/**/*` (already set in root `pyproject.toml`) |
| DB assertions | Open `Session()` directly, don't go through the API |
| Fixture scope | Session for everything except function-scoped cleanup fixtures |
| Test marker | `@pytest.mark.asyncio(loop_scope="session")` always |
| No `__init__.py` | Tests run under `--import-mode=importlib` |

## Dependencies

`httpx` and `pytest-asyncio` live in the workspace root `pyproject.toml` dev group; `pytest` is declared by the `ticketmaster` service package. `poetry install` from the root brings them all in.
