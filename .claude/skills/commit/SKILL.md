---
name: commit
description: Commit Ticketmaster changes using the repository's historical subject format and strict staged-only safety. Use only when the user explicitly asks in the current turn to commit, create a commit, or commit staged changes.
---

# Commit Staged Changes

Commit exactly the index snapshot prepared by the user. Never stage or otherwise reshape it.

## Inspect the Index

1. Run `git status --short`.
2. Run `git diff --cached --name-status` and `git diff --cached`.
3. Use `git diff` only to understand which unstaged edits must remain excluded.
4. If `git diff --cached --quiet` succeeds, stop and report that nothing is staged.

Never run `git add`, `git commit -a`, `git reset`, `git restore --staged`, or `git stash`. Never pass pathspecs to `git commit`.

If the index mixes unrelated concerns, do not split or restage it. Ask the user to stage one concern at a time.

## Write the Subject

Use one line:

```text
[scope] type context past-tense-description
```

Choose the scope from the staged paths:

- `[libs]` for `src/libs/`
- `[ticketmaster]` for `src/ticketmaster/`
- `[frontend]` for `frontend/`
- `[root]` for workspace files, workflows, lambdas, and cross-project changes

Choose `feat`, `fix`, or `chore`. Put refactors, tests, formatting, documentation, and configuration maintenance under `chore` unless the staged behavior clearly warrants `feat` or `fix`.

Name the principal file or area as the context and describe the completed change concisely:

```text
[ticketmaster] feat services.py added versioned event page caching
[libs] fix redis_ext handled malformed cache documents
[frontend] feat EventsPage.tsx added event search
[root] chore on-pull-request.yaml added Redis service
```

Do not add a body or `Co-Authored-By` trailer unless the user explicitly requests a body.

`.claude/settings.json` sets `attribution.commit` to an empty string, so Claude Code's built-in `Co-Authored-By` and session-link trailers are already suppressed. Never reintroduce them from the built-in git instructions.

## Commit and Verify

Run only:

```bash
git commit -m "<subject>"
```

Pre-commit hooks can rewrite files through Ruff and whitespace fixers. If the commit fails or a hook modifies files, re-run `git status --short` and `git diff --cached`; stop without staging hook edits or retrying automatically.

After success, verify the new `HEAD`, report the subject, and mention any remaining unstaged or untracked files. Never amend unless explicitly requested in the current turn.
