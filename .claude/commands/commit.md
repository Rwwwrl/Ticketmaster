Create a commit for staged changes.

## Rules

**Format:** `[scope] <type> <context> <description>`

**Scope** (where the change lives):
- `[libs]` - anything under `src/libs/` (shared infrastructure: `sqlmodel_ext`, `alembic_ext`, `datetime_ext`, `settings`, `common`, …)
- `[ticketmaster]` - anything under `src/ticketmaster/` (the deployable service, including its `models.py`, `migrations/`, `alembic.ini`, `env.dev.yaml`, service-level `pyproject.toml`, …)
- `[root]` - workspace-level files (root `pyproject.toml`, `docker-compose.yaml`, `justfile`, `documentation/`, `.gitignore`, `.pre-commit-config.yaml`, `.vscode/`, …)

**Type** (what kind of change):
- `feat` - new functionality
- `fix` - bug fix
- `chore` - formatting, docs, refactoring

**Context:** Main file or area affected (e.g. `models.py`, `pyproject.toml`, `system_design.md`)

**Description:** One line, concise. No detailed explanations.

**Do not include** `Co-Authored-By` lines in commits.

**Examples:**
```
[libs] feat sqlmodel_ext/base_model.py added BaseSqlModel with before_update listener
[libs] chore alembic_ext/env_helpers.py simplified URL rewrite for psycopg
[ticketmaster] feat models.py added Event/User/Ticket tables
[ticketmaster] fix migrations/env.py registered models on metadata
[ticketmaster] chore pyproject.toml moved test deps from root to service
[root] chore documentation/system_design.md removed is_sold_out
[root] chore pyproject.toml bumped ruff to 0.15.10
```

## Steps

1. Run `git status` and `git diff --staged` to understand what is being committed.
2. If nothing is staged, stage the relevant changed files (prefer specific files over `git add .`).
3. Draft a commit message following the format above.
4. Create the commit.
