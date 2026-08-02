---
name: fastapi
description: Apply Ticketmaster FastAPI architecture and conventions. Use for HTTP app setup, routes, dependencies, auth, request or response schemas, serialization, middleware, lifespan, health endpoints, and FastAPI endpoint tests.
---

# Ticketmaster FastAPI

Implement HTTP changes within the protocol-first service layout and keep business logic out of routes.

## Place Code

- Keep app construction, lifespan, middleware, health probes, and router registration in `src/ticketmaster/ticketmaster/http/main.py`.
- Keep public v1 endpoints in `http/v1/routes.py`, dependencies in `http/v1/dependencies.py`, and HTTP-only schemas in `http/v1/schemas/`.
- Keep admin HTTP code under `admin/http/`.
- Keep shared middleware and schema bases under `src/libs/libs/fastapi_ext/`.
- Keep shared DTOs at `ticketmaster/schemas/dtos.py`, optional business services under `ticketmaster/services/`, repositories in `ticketmaster/repositories.py`, and DTO-to-response conversion in `ticketmaster/serializers.py`.

Use either `routes -> repositories -> models` or `routes -> services -> repositories -> models`. Call a repository directly for straightforward data access. Introduce a service only when the endpoint needs business logic or orchestration; do not add a pass-through service merely to preserve a layer.

## Implement an Endpoint

1. Define request fields in a `BaseRequestSchema` subclass and output fields in a `BaseResponseSchema` subclass. Make new fields required unless they are genuinely optional.
2. Put reusable validation, auth, and cursor decoding in dependencies.
3. Use `Annotated[ValueType, Depends(dependency)]` when a dependency returns a value. Use decorator-level `dependencies=[Depends(guard)]` for guard-only checks.
4. Declare an explicit `response_model`, status code, and fully typed `async def` endpoint.
5. Open the transaction at the route boundary:

   ```python
   async with Session() as session, session.begin():
       dto = await EventRepository.get_by_id(session=session, _id=event_id)
   ```

6. Pass the session into the repository directly, or into a service when business logic warrants one. Do not commit inside services or repositories.
7. Translate expected domain exceptions to `HTTPException` at the HTTP boundary. Do not leak database or cache exceptions.
8. Serialize DTOs into response schemas through `serializers.py`. Do not return ORM models.

For PATCH-style payloads, type optional fields accurately and use `model_dump(exclude_unset=True)` so omitted fields differ from explicit values.

Use keyword arguments, mandatory type annotations, and async I/O. Prefix module and class internals with `_`.

## Preserve Application Lifecycle

The production lifespan must:

- Configure logging and Sentry.
- Initialize the async SQLModel engine and bind the global `Session`.
- Configure async Redis with `decode_responses=False`.
- Bind optional ECS task-role credentials.
- Close Redis and dispose the engine on shutdown.

Keep `/health` dependency-free for liveness. Keep `/readiness_check` dependent on PostgreSQL and Redis. Keep docs and OpenAPI disabled in data-sensitive environments.

Preserve the shared middleware behavior and effective order: unhandled exceptions, security headers, request/response logging, request ID, and the 1 MiB request-body limit. Add focused middleware tests when changing it.

## Test the HTTP Boundary

Use the fixtures in `src/ticketmaster/ticketmaster/tests/conftest.py`. The test app registers routers directly and does not run the production lifespan, so rely on the SQLModel and Redis fixtures instead of production initialization.

- Use `httpx.AsyncClient` with `ASGITransport`.
- Use session-scoped async loops consistently with the repository tests.
- Override dependencies for authentication or failure paths and always clear overrides after `yield`.
- Cover success, request validation, authorization, domain-error mapping, persistence, and response shape.
- Keep 204 responses and return annotations coherent.

Run focused tests first, then repository checks:

```bash
just up-infra
poetry run pytest path/to/test_file.py -s
poetry run ruff check .
poetry run ruff format --check .
```

For a complete CI-equivalent test run:

```bash
poetry run pytest --cov=src/libs/libs --cov=src/ticketmaster/ticketmaster --cov-report=term-missing --cov-fail-under=75
```

Bump the affected package version when changing code under `src/libs/` or `src/ticketmaster/`; pull-request CI enforces version changes.
