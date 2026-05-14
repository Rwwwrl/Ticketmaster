---
name: fastapi
description: Encodes how ticketmaster wires FastAPI — lifespan + middleware stack, versioned router layout, schema tiers (DTO → BaseRequestSchema/BaseResponseSchema), and a two-layer error model where middleware owns cross-cutting responses and HTTPException is the right tool for per-endpoint cases. Use whenever writing or modifying anything under `http/`, adding endpoints, registering middleware, configuring lifespan, designing request/response schemas, or setting up the test app — even if the user does not say "fastapi" explicitly. Trigger phrases include "fastapi", "endpoint", "route", "router", "APIRouter", "middleware", "lifespan", "request schema", "response schema", "Depends", "HTTPException", "exception handler", "uvicorn", "http/main.py", "http/v1".
---

# FastAPI

## Module Layout

The HTTP protocol lives at `src/ticketmaster/ticketmaster/http/`. Versioning is done by directory, not by router prefix:

```
http/
    __init__.py
    main.py              # FastAPI app, lifespan, middleware
    v1/
        __init__.py      # re-exports v1_router
        routes.py        # APIRouter() + endpoints
        schemas/
            request_schemas.py
            response_schemas.py
```

`http/v1/__init__.py` is one line: `from ticketmaster.http.v1.routes import v1_router` plus `__all__ = ["v1_router"]`. Future versions go in sibling `v2/` folders. The same `v1/`-style versioning is mirrored in `grpc/` and `background_tasks/` when they appear.

## App + Lifespan

`http/main.py` owns the single `FastAPI` instance and a single `@asynccontextmanager` lifespan. The lifespan acquires every external resource the service needs, stashes them on `app.state`, and tears them down in reverse on shutdown. This is the only place resources are created — endpoints never construct engines, brokers, or channels.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging(level=settings.log_level, process_type=ProcessTypeEnum.FASTAPI)
    setup_sentry(release=version("ticketmaster"))
    engine = init_sqlmodel_engine(db_url=settings.postgres_db_url)
    Session.configure(bind=engine)
    app.state.sqlmodel_engine = engine
    yield
    await engine.dispose()


_is_sensitive = is_data_sensitive_env(environment=settings.environment)
app = FastAPI(
    title="Ticketmaster",
    version=version("ticketmaster"),
    description="...",
    lifespan=lifespan,
    docs_url=None if _is_sensitive else "/docs",
    redoc_url=None if _is_sensitive else "/redoc",
    openapi_url=None if _is_sensitive else "/openapi.json",
)
```

Two non-obvious rules:

- **`version()` from `importlib.metadata`** is the only source of the version string — never hardcode.
- **Docs/redoc/openapi are disabled in sensitive envs** (`is_data_sensitive_env` from `libs.common`). Schemas leak too much in prod; this gating is part of the convention, not optional.

## Middleware Stack

Five middlewares in this exact order. Starlette runs `add_middleware` calls in reverse, so the first one added is the *innermost*, and the last one added is the *outermost*. Order matters because the outermost layer must be able to reject traffic before later layers parse it.

```python
app.add_middleware(UnhandledExceptionMiddleware)        # innermost — last line of defense
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestResponseLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RequestBodyLimitMiddleware, max_body_size=1_048_576)  # outermost
```

What each does and why it sits where it does:

| Middleware | Role | Why this position |
| --- | --- | --- |
| `RequestBodyLimitMiddleware` | 413 if `Content-Length` > 1 MiB or stream exceeds it | Outermost so we reject oversized bodies *before* logging or ID generation reads them |
| `RequestIdMiddleware` | Reads `X-Request-ID`, validates (≤256 chars, ASCII-printable), echoes back, sets `request_id_var` ContextVar | Above logging so every log line carries the ID |
| `RequestResponseLoggingMiddleware` | Logs method/path/status/timing; redacts non-allow-listed headers; truncates bodies at 10 KB; skips `/health`, `/readiness_check`, `/metrics`, docs paths | Just inside RequestId so it can read the ID |
| `SecurityHeadersMiddleware` | Adds `X-Content-Type-Options: nosniff` and HSTS | Inside logging so the headers it adds are observable on the response |
| `UnhandledExceptionMiddleware` | Catches every uncaught `Exception`, logs with `extra={...}`, returns 500 `{"detail": "Internal Server Error"}` | Innermost — closest to the route, catches everything domain code raises |

All five live in `src/libs/libs/fastapi_ext/middlewares/` and are imported from `libs.fastapi_ext.middlewares`.

`setup_fastapi_prometheus(app=app)` runs **after** middleware and router registration in `main.py`. This is the last call before the file ends.

## Router Registration

A bare `APIRouter()` per version, no prefix and no tags on the router itself. The prefix is applied at include time. This keeps the router file decoupled from URL versioning so renaming `/v1` → `/v2` is one edit in `main.py`.

```python
# http/v1/routes.py
v1_router = APIRouter()

@v1_router.get("/events/", status_code=status.HTTP_200_OK,
               response_model=response_schemas.EventsPageResponseSchema)
async def list_events_page(...) -> response_schemas.EventsPageResponseSchema:
    ...

# http/main.py
app.include_router(router=v1_router, prefix="/v1")
```

## Endpoint Conventions

- **`async def` always.** Sync endpoints are not used.
- **Explicit `status_code=`** on every decorator using `from fastapi import status` (e.g. `status.HTTP_201_CREATED`). Don't rely on the 200 default — being explicit is part of the route's contract.
- **`response_model=`** matches the return-type annotation. Both are present; they are not redundant — `response_model` drives the OpenAPI schema and serialization, the annotation drives type checkers.
- **Bodyless responses** return `Response(status_code=...)` (from `starlette.responses`), not `None`.
- **Query params use `Annotated[T, Query(...)]`** with constraints (`ge`, `le`) inline.
- **Schema imports are by module, not class**: `from ticketmaster.http.v1.schemas import response_schemas`, then `response_schemas.EventResponseSchema`. This keeps call sites self-documenting and avoids name collisions across versions.
- **All call-site arguments are keyword arguments** (per `AGENTS.md`). Single-arg cases like `len(items)` are the only exception.

## Wiring Things Without `Depends()`

There are no `Depends()` callsites in the project today. This is not a rule against using it — the situations that would need it (per-request auth, per-request transactional scoping, request-scoped repositories) haven't come up yet. So far, simpler patterns have been enough:

| What you'd inject | What we do today |
| --- | --- |
| Settings | Module-level singleton: `from ticketmaster.settings import settings` |
| DB session | `async with Session() as session, session.begin():` inside the endpoint. `Session` is the module-level `async_sessionmaker` bound during lifespan |
| Engine / broker / gRPC channel | Stashed on `app.state.<x>` during lifespan; read via `request.app.state.<x>` |
| Per-request context (request id) | `contextvars.ContextVar` set by middleware, read anywhere downstream |
| Repositories | Stateless classmethod containers — `EventRepository.get_all_paginated(session=session, ...)` |

When a real need for `Depends()` arises (e.g. an auth dependency that has to run before the route body), introduce it then — but check whether one of the above patterns covers the case first, since they keep domain code free of FastAPI imports and let the same repository work unchanged from gRPC or background-task entrypoints.

## Schema Tiers

Three layers, each subclassing the next:

```
DTO (libs.common.schemas.dto)            frozen=True, extra="ignore"
  ├── BaseRequestSchema  (libs.fastapi_ext.schemas.base_schemas)
  └── BaseResponseSchema (libs.fastapi_ext.schemas.base_schemas)
```

- **DTOs** (`schemas/dtos.py`, suffix `DTO`) — internal data carriers between layers. Repositories return DTOs, never SQLModels. Constructed via `EventDTO.from_sqlmodel(model=event)` or `EventDTO(**event.model_dump())`.
- **Request schemas** (`http/v1/schemas/request_schemas.py`, suffix `RequestSchema`) — extend `BaseRequestSchema`. Used as endpoint body parameters.
- **Response schemas** (`http/v1/schemas/response_schemas.py`, suffix `ResponseSchema`) — extend `BaseResponseSchema`. Used as `response_model=` and the return-type annotation.

Conversion DTO → ResponseSchema goes through dedicated serializer classes in `serializers.py` named `To<Schema>` (e.g. `ToEventResponseSchema.serialize(dto=dto)`). Don't construct response schemas inline from DTO fields in routes — go through the serializer so the mapping has one home.

All schemas inherit `frozen=True` from `DTO`, so they're immutable after construction.

## Error Handling

Two layers with different jobs. They are not in conflict — picking the right one is the whole convention.

**Middleware** owns *cross-cutting* responses — the same answer regardless of which route was hit:

- **422** — FastAPI's built-in Pydantic validation response. Don't intercept it.
- **400** — `RequestIdMiddleware` for malformed `X-Request-ID`.
- **413** — `RequestBodyLimitMiddleware` for oversized bodies.
- **500** — `UnhandledExceptionMiddleware` catches anything that escapes a route, logs with structured `extra={...}`, and returns `{"detail": "Internal Server Error"}`.

**`HTTPException`** is the right tool when a specific route or dependency needs to signal an HTTP-level error tied to *that* endpoint's logic. It is fully allowed and already used in the project — see `http/v1/routes.py` (400 on `IntegrityError` when a duplicate user is created) and `http/v1/dependencies.py` (401 from `validate_lambda_jwt` on a bad token). FastAPI converts the raise into a JSON response with the right status — that is the point of the type.

A few worked examples to calibrate when to reach for it:

- Endpoint catches a known DB constraint violation and wants to surface a clean 400 with a meaningful `detail` → raise `HTTPException` at the catch site. Don't invent a domain exception just to bounce it back through middleware.
- Auth dependency rejects a malformed or expired token → raise `HTTPException(401)` from the dependency. The dependency runs before the route body, so this is the natural shape.
- An expected business outcome (e.g. "event not found", "seat already booked") that the endpoint *intends* to signal as a specific status → `HTTPException` at the route layer is fine. The repository/service still raises a plain domain exception or returns `None`; the route is the layer that translates it.

What stays out of `HTTPException`: anything genuinely *unexpected*. Bugs, network blips, programmer errors — let those propagate to `UnhandledExceptionMiddleware` so they're logged uniformly and don't leak internals.

**`@app.exception_handler` / `app.add_exception_handler`** are not used today (no domain exception type has warranted a centralized mapping yet) but they are not banned. Same framing as `Depends()`: introduce one when a real need shows up — typically when a single domain exception is raised from many routes and always maps to the same status. Until then, raising `HTTPException` at the call site is simpler and just as correct.

Where the line falls in practice:

| Situation | Tool |
| --- | --- |
| Cross-cutting (body limit, request id, security headers, last-resort 500) | Middleware |
| Per-endpoint or per-dependency HTTP-level error | `HTTPException` at the raise site |
| Domain exception class raised from many places that always maps to the same status | Register an exception handler — when this case actually appears |
| Truly unexpected error | Let it bubble to `UnhandledExceptionMiddleware` |

Domain code (repositories, services, schemas, anything outside `http/`) still must not import `HTTPException`. The translation lives in the route or the dependency — that is the layer that knows the protocol is HTTP. The same repository should be reusable from `grpc/` or `background_tasks/` without change.

## Testing the App

Tests do **not** import the production `app`. The `fastapi_app` fixture in `tests/conftest.py` builds a fresh bare `FastAPI()`, attaches the engine to `app.state`, and includes only `v1_router` — middleware and lifespan are bypassed. HTTP calls go through `httpx.AsyncClient` over `ASGITransport`. See the `testing` skill for the full fixture pattern.

If a test needs to verify middleware behavior (request id echo, body limit), `add_middleware` it onto the test app explicitly — don't pull in the production stack wholesale.

## Mental Model

FastAPI is the HTTP entrypoint, not the architecture. The `http/` folder is one of several sibling protocol folders; everything domain-shaped (repositories, DTOs, settings) is plain Python that knows nothing about FastAPI. Lifespan wires resources, middleware handles cross-cutting concerns, routes and dependencies are thin adapters that translate between the protocol and the domain. `Request`, `Depends`, and `HTTPException` are perfectly at home inside `http/` — that is what those types are for. The smell test is the *direction* of the import: if code *outside* `http/` (a repository, a service, a schema) starts importing FastAPI types, it's probably in the wrong folder.
