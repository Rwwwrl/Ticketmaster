# Ticketmaster

Ticketmaster is an online platform where anyone can browse and book tickets to live events — sport games, concerts, and theater shows.

## Service Internal Architecture

Ticketmaster is a single deployable service at `src/ticketmaster/`. Shared infrastructure lives in `src/libs/` as a separate Poetry package.

The top-level split inside the service is by **communication protocol** (`http/`, `grpc/`, `background_tasks/`), not by technical layer. Each protocol folder has its own `main.py` with protocol-specific setup (FastAPI app, broker config, etc.). Shared domain code — models, repositories, schemas, settings — lives at the service root and is accessible from all protocol folders.

Not every protocol folder exists yet. Today only `http/` is in use; `grpc/` and `background_tasks/` are planned.

### Service Module Structure

```
ticketmaster/
    settings.py              # Service configuration (shared across protocols)
    utils.py                 # Shared utilities (e.g., engine init)
    models.py                # Database models (flat — no per-aggregate folders)
    enums.py                 # Enum classes (flat)
    repositories.py          # Data access layer (shared)
    schemas/
        dtos.py              # Shared DTOs
    http/
        __init__.py
        main.py              # FastAPI app, lifespan, middleware
        routes.py            # API endpoints (FastAPI router)
        schemas/
            request_schemas.py
            response_schemas.py
    grpc/                    # Future — gRPC protocol support
        __init__.py
        main.py
    background_tasks/        # Future — background tasks (TaskIQ + RabbitMQ)
        __init__.py
        main.py              # Broker setup, worker lifecycle
        tasks.py             # Task definitions
```

Additional common files (add as needed): `serializers.py`, `exceptions.py`.

Keep the domain layer flat. Do not split `models.py` / `enums.py` into per-aggregate folders.

### Layer Dependency Direction

```
http/routes.py  →  services.py  →  repositories.py  →  models.py
    |                  |                  |
    v                  v                  v
http/schemas/       schemas/           schemas/
  request            dtos               dtos
  response                              nested_models
    |
    v
serializers.py  (DTO → response_schemas)
```

Routes depend on services, services depend on repositories, repositories depend on models. Schemas are used across layers. Never import routes from services or repositories.

### Shared Library

`src/libs/` is a separate Poetry package (`ticketmaster-libs`) with shared code. The service depends on it via path dependency: `ticketmaster-libs = { path = "../libs", develop = true }`.

## Development

**Python version:** 3.14

**Running Python:** Always use `poetry run python`, not `python` or `python3`

**Adding dependencies:** Use `poetry add` command, never edit `pyproject.toml` directly:

```bash
poetry add fastapi              # Add main dependency
poetry add --group dev pytest   # Add dev dependency
```

**Linting & Formatting:** Uses **ruff** (line length: 120):

```bash
poetry run ruff check --fix .
poetry run ruff format .
```

**Task runner:** Uses `just` (see `justfile` for available commands).

**Pre-commit:** Uses `pre-commit` hooks (see `.pre-commit-config.yaml`).

## Coding Standards

- **Async first.** Use `async def` for endpoints, service methods, and I/O operations. Sync code is the exception, not the rule.
- **Pydantic for data models.** Use Pydantic (`BaseModel`) when defining data containers, schemas, configs, or anything that benefits from validation and serialization. Plain classes are fine when Pydantic adds no value — not everything needs to be a Pydantic model.
- **Type annotations are mandatory.** All functions, methods, and class attributes must have type hints.
- **Enum naming.** All enum classes must use the `Enum` suffix (e.g., `EnvironmentEnum`, `LogLevelEnum`, `OrderStatusEnum`).

### Named Arguments

**Always use keyword arguments.** Never use positional arguments when calling functions or methods.

```python
# Bad - positional arguments
user = create_user("John", "john@example.com", True)

# Good - keyword arguments
user = create_user(name="John", email="john@example.com", is_active=True)
```

**Exception:** Single-argument calls where the meaning is obvious (e.g., `len(items)`, `str(value)`).

### Code Comments

**Rarely write comments.** When needed, use `# NOTE @author` for non-obvious context:

```python
# NOTE @sosov: Skip intermediate batches during historical pulls.
```

**When to use NOTE:** non-obvious business logic, external API quirks, important constraints.

**Never comment:** obvious code, variable names, standard operations.

### Encapsulation

**Prefix everything internal with `_`.** If it's not part of the public API, it gets an underscore. Encapsulation brings clarity — readers instantly know what's internal and what's meant to be used externally. This applies to:

- **Class attributes** — internal state set in `__init__`
- **Class methods** — helpers not called from outside the class
- **Module-level functions** — helpers used only within the module
- **Module-level classes** — implementation details not imported elsewhere
- **Module-level constants** — values used only within the module

```python
# Module-level internals are private
_TOO_LARGE_BODY = json.dumps({"detail": "Request body too large"}).encode()


class _BodyTooLargeError(Exception):
    pass


def _get_content_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    for name, value in headers:
        if name == b"content-length":
            return int(value)
    return None


# Class internals are private
class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self._app = app
        self._max_body_size = max_body_size
```

### Default Arguments and Fallbacks

**Think twice before adding defaults.** They can hide bugs by silently accepting missing data.

```python
# Bad - caller should explicitly decide
def send_notification(user: User, priority: str = "normal"): ...

# Good - well-established convention
def paginate(items: list, page: int = 1, page_size: int = 20): ...
```

**Acceptable defaults:** pagination, logging levels, retry counts, optional boolean flags.

**Avoid defaults:** when callers should make explicit choices, or when values are context-dependent.

**Avoid fallbacks:** Don't use `value or default_value` patterns to silently handle missing data. If a value is required, let it fail explicitly rather than substituting a fallback that hides the real problem.

**New fields should be required by default.** When adding fields to models, schemas, or dataclasses, make them required unless there's a clear reason for optionality. Don't preemptively add `Optional`, `None` defaults, or `= Field(default=...)` just to avoid migration issues or "be safe."

```python
# Bad - making fields optional "just in case"
class User:
    name: str
    email: str
    role: str | None = None  # Why optional? Every user needs a role.

# Good - required unless truly optional
class User:
    name: str
    email: str
    role: str  # Required. Caller must provide it.
```
