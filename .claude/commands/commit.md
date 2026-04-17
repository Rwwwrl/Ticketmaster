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

## When to commit

**Only commit when this skill is invoked in the current turn, and only commit what the user has already staged.** Two hard rules:

- **Never commit on your own.** Not after producing an edit, not because the user approved a commit earlier in the conversation, not because "it seems like a good stopping point". Prior `/commit` approvals apply only to the commit they were given for. If changes are in the working tree and the user has not just invoked `/commit`, leave them alone so the user can review.
- **Never stage files on behalf of the user.** Staging is how the user tells you what to commit. If `git status` shows nothing staged when `/commit` is invoked, stop and tell the user — do not run `git add`.

## Steps

1. Run `git status` and `git diff --staged` to see what the user has staged.
2. If nothing is staged, stop and tell the user — do not stage anything yourself.
3. If the staged changes cover multiple unrelated concerns, split them into separate commits (one per concern). Otherwise a single commit is fine.
4. Draft a message for each commit in the format above and create the commits.
