---
name: git-branch
description: Derive and create a safe Ticketmaster Git branch from a task description. Use when the user asks to create, start, name, or switch to a new branch for a task, issue, feature, fix, refactor, or maintenance change.
---

# Create a Git Branch

Create one concise branch from the task description without changing or synchronizing repository history.

## Choose the Base

1. Inspect the current branch, `HEAD` SHA, and `git status --short`.
2. Use the user-specified base when provided.
3. Otherwise, branch from the current `main`.
4. If the current branch is not `main` and no base was specified, stop and ask whether to use current `HEAD` or `main`. Do not silently stack work on another feature branch.

Do not fetch, pull, reset, rebase, merge, stash, or discard changes. Existing staged, unstaged, and untracked state moves to the new branch; report that state after creation.

## Derive the Name

Use the dominant repository convention:

```text
prefix/lowercase-kebab-description
```

Select the prefix:

- `feature/` for new behavior; use this by default
- `fix/` for an explicit defect
- `refactor/` for behavior-preserving restructuring
- `chore/` for maintenance or configuration
- Honor an explicit user-provided prefix

Remove filler words and punctuation. Keep the slug short and specific. If the task includes an issue key, preserve it in uppercase before the slug:

```text
feature/event-cache-versioning
feature/TM-123-add-event-search
fix/redis-namespace-miss
refactor/services-and-tests-structure
```

## Validate and Create

1. Validate with `git check-ref-format --branch "<name>"`.
2. Check both `refs/heads/<name>` and the existing `refs/remotes/origin/<name>` for collisions. Do not fetch automatically.
3. Create the branch with `git switch -c "<name>"` from the resolved base.
4. Verify the active branch and report its name, base SHA, and carried working-tree state.

If the name already exists, stop and report the collision. Do not switch to, delete, rename, or overwrite an existing branch without explicit direction.
