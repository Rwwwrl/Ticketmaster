Create a commit for staged changes.

## Rules

**Format:** `[scope] <type> <context> <description>`

**Scope** (where changes were made):
- `[root]` - root-level files (configs, deps, CI, tooling)
- `[<module>]` - specific module under `src/`, e.g. `[events]`, `[tickets]`, `[api]`
- `[docs]` - documentation changes (e.g. `documentation/system_design.md`)

**Type** (what kind of change):
- `feat` - new functionality
- `fix` - bug fix
- `chore` - formatting, docs, refactoring

**Context:** Main file or area affected (e.g. `routes.py`, `pyproject.toml`, `system_design.md`)

**Description:** One line, concise. No detailed explanations.

**Do not include** `Co-Authored-By` lines in commits.

**Examples:**
```
[events] feat routes.py added GET /events/search endpoint
[tickets] fix repository.py fixed conditional UPDATE for reservation
[root] chore pyproject.toml bumped ruff to 0.15.10
[docs] chore system_design.md clarified caching invalidation
```

## Steps

1. Run `git status` and `git diff --staged` to understand what is being committed.
2. If nothing is staged, stage the relevant changed files (prefer specific files over `git add .`).
3. Draft a commit message following the format above.
4. Create the commit.
