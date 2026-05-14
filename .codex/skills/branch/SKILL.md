---
name: branch
description: Create a new git branch from the current conversation context using the type/short-description naming convention, such as feature/add-user-auth or fix/login-redirect-loop. Use when the user invokes /branch or asks to create, start, or switch to a new branch.
---

# Branch

Create a new git branch named from the current conversation context.

## Naming format

`<type>/<short-description>`

**Type** (what kind of work):
- `feature` - new functionality
- `fix` - bug fix
- `chore` - formatting, deps, configs, small maintenance
- `refactor` - restructuring without behavior change
- `docs` - documentation only

**Short description:**
- kebab-case (lowercase, words joined by `-`)
- 3-6 words
- describe the *thing being changed*, not the action — drop filler verbs like `add`, `make`, `update` when they don't add meaning
- no trailing slashes, no leading articles (`a`, `the`)

**Examples:**
```
feature/add-all-api-routes
feature/event-search-endpoint
fix/migration-env-models
fix/postgres-url-secret-injection
chore/bump-ruff-0.15.10
refactor/split-repositories-by-aggregate
docs/system-design-cleanup
```

## Picking the name

1. Look at the recent conversation. What is the user actually about to work on? That's the description.
2. Pick the type from the kind of change implied (new code → `feature`, bug → `fix`, etc.). When in doubt, `feature` is the safe default.
3. If the user explicitly says the type or the name, use what they said verbatim — don't second-guess it.
4. If the context is too thin to name the branch confidently, ask the user for a one-line description before creating anything.

## Steps

1. Run `git status` and `git branch --show-current` to confirm the working state and current branch.
2. Decide on the new branch name from the conversation context.
3. Tell the user the name you picked before creating the branch, so they can redirect if it's off.
4. Run `git checkout -b <name>` from the current HEAD. Do not reset, stash, or rebase on the user's behalf.
5. Report the new branch name to the user.
