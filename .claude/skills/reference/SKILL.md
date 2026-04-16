---
name: reference
description: Look up how a topic (e.g., fastapi, postgres, testing, code-conventions) is handled in the eshop2 reference project at /Users/aleksejsosov/code_folder/home/eshop2 — pulls both the skill documentation and concrete code examples from the actual src/ tree. Use when the user asks "how does eshop2 do X" or invokes `/reference <topic>`.
---

# reference

The user keeps a richer reference project at `/Users/aleksejsosov/code_folder/home/eshop2` that the current ticketmaster project draws style and patterns from. This skill is the lookup tool for it.

## When to invoke

- The user types `/reference <topic>` (e.g. `/reference fastapi`, `/reference postgres`).
- The user asks "how does eshop2 handle …", "show me the eshop pattern for …", "what's our convention for …" — without naming a specific file.
- Before recommending a non-trivial pattern (FastAPI lifespan, SQLModel session, pytest fixtures, etc.) — sanity-check the eshop2 implementation first instead of going from memory.

## Available topics

The reference project ships its own `.claude/skills/` directory. Topic names map 1:1 to those skill folders:

| Topic | Covers |
|---|---|
| `code-conventions` | imports, schemas, DTOs, module structure, `__init__` rules |
| `fastapi` | HTTP service, routers, lifespan, middleware, health checks |
| `postgres` | SQLModel, Alembic migrations, TimescaleDB hypertables |
| `testing` | pytest async, httpx fixtures, conftest patterns |
| `setup-docs` | docs/setup-env.md maintenance |
| `update-skill` | meta — how to author SKILL.md files |
| `version` | bump versions across pyproject.toml files |

If the user asks for a topic not in this list, fall back to `Grep` over `/Users/aleksejsosov/code_folder/home/eshop2/src/` for the keyword.

## How to run a lookup

Given a topic `<T>` (e.g. `fastapi`):

1. **Read the skill doc:** `Read /Users/aleksejsosov/code_folder/home/eshop2/.claude/skills/<T>/SKILL.md`. Quote the directives that apply.
2. **List the references directory** (if it exists): `Glob /Users/aleksejsosov/code_folder/home/eshop2/.claude/skills/<T>/references/**`. Read the file(s) most relevant to the user's question — don't dump everything.
3. **Pull a concrete code example from the actual codebase.** Pick the most representative service for the topic:
   - `fastapi`, `postgres` → `/Users/aleksejsosov/code_folder/home/eshop2/src/services/wearables/` (the most complete service)
   - `code-conventions`, `testing` → grep across `src/` and `src/libs/`
   Use `Grep` with a topic-specific pattern (e.g. `fastapi` → search for `FastAPI(`, `lifespan`, `APIRouter`; `postgres` → search for `AsyncEngine`, `sessionmaker`, `Session.exec`).
4. **Synthesize the answer for ticketmaster.** Two short blocks:
   - **From eshop2:** quote the rule + 1-2 file:line code references with a short snippet.
   - **For ticketmaster:** translate. Strip eshop-specific imports (`libs.fastapi_ext`, `libs.sqlmodel_ext`, etc.) — those don't exist here.

## Permissions

This Claude session already has `Read`, `Glob`, and `Grep` allowed for `/Users/aleksejsosov/code_folder/home/eshop2/**` (configured in `.claude/settings.local.json`), so no permission prompts are needed.

## Things to avoid

- Don't copy eshop2 imports verbatim — `from libs.fastapi_ext import ...`, `from libs.sqlmodel_ext import ...` will not resolve. Always translate to plain stdlib / third-party equivalents.
- Don't recommend `import-linter` contracts — ticketmaster doesn't use it.
