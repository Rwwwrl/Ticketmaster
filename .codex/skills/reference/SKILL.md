---
name: reference
description: Look up how a topic such as fastapi, postgres, testing, or code-conventions is handled in the eshop2 reference project at /Users/aleksejsosov/code_folder/home/eshop2. Use when the user asks how eshop2 handles something or invokes /reference with a topic.
---

# Reference

The user keeps a richer reference project at `/Users/aleksejsosov/code_folder/home/eshop2` that the current ticketmaster project draws style and patterns from. This skill is the lookup tool for it.

## When to invoke

- The user types `/reference <topic>` (e.g. `/reference fastapi`, `/reference postgres`).
- The user asks "how does eshop2 handle …", "show me the eshop pattern for …", "what's our convention for …" — without naming a specific file.
- Before recommending a non-trivial pattern (FastAPI lifespan, SQLModel session, pytest fixtures, etc.) — sanity-check the eshop2 implementation first instead of going from memory.

## Topic Hints

Use these topic labels to guide source searches:

| Topic | Covers |
|---|---|
| `code-conventions` | imports, schemas, DTOs, module structure, `__init__` rules |
| `fastapi` | HTTP service, routers, lifespan, middleware, health checks |
| `postgres` | SQLModel, Alembic migrations, TimescaleDB hypertables |
| `testing` | pytest async, httpx fixtures, conftest patterns |
| `setup-docs` | docs/setup-env.md maintenance |
| `update-skill` | meta — how to author SKILL.md files |
| `version` | bump versions across pyproject.toml files |

If the user asks for a topic not in this list, search `/Users/aleksejsosov/code_folder/home/eshop2/src/` for the keyword.

## How to run a lookup

Given a topic `<T>` (e.g. `fastapi`):

1. Search the reference project's docs and source with `rg` using topic-specific terms.
2. Pull a concrete code example from the actual codebase. Pick the most representative service for the topic:
   - `fastapi`, `postgres` → `/Users/aleksejsosov/code_folder/home/eshop2/src/services/wearables/` (the most complete service)
   - `code-conventions`, `testing` → grep across `src/` and `src/libs/`
   Use `rg` with a topic-specific pattern (e.g. `fastapi` → search for `FastAPI(`, `lifespan`, `APIRouter`; `postgres` → search for `AsyncEngine`, `sessionmaker`, `Session.exec`).
3. Synthesize the answer for ticketmaster. Two short blocks:
   - **From eshop2:** cite the source file and line references, with only the minimal snippet needed.
   - **For ticketmaster:** translate. Strip eshop-specific imports (`libs.fastapi_ext`, `libs.sqlmodel_ext`, etc.) — those don't exist here.

## Permissions

If sandboxing blocks reads or searches under `/Users/aleksejsosov/code_folder/home/eshop2/**`, request approval for the specific `rg`, `sed`, or file-read command.

## Things to avoid

- Don't copy eshop2 imports verbatim — `from libs.fastapi_ext import ...`, `from libs.sqlmodel_ext import ...` will not resolve. Always translate to plain stdlib / third-party equivalents.
- Don't recommend `import-linter` contracts — ticketmaster doesn't use it.
