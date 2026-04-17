---
name: version
description: Check and update versions across ticketmaster pyproject.toml files. Use when bumping versions, checking version consistency, or after changing dependencies. Trigger phrases include "check versions", "bump version", "version check", "update version".
user_invocable: true
---

# Version Management

Ticketmaster is a two-package workspace: one shared library and one deployable service. Versions are enforced by CI — any code change under `src/libs/` or `src/ticketmaster/` requires a version bump in the matching `pyproject.toml` (see `.github/workflows/on-pull-request.yaml::check_versions`).

## Pyproject.toml Locations

| Package | Path | Poetry name |
|---------|------|-------------|
| Shared library | `src/libs/pyproject.toml` | `ticketmaster-libs` |
| Service | `src/ticketmaster/pyproject.toml` | `ticketmaster` |

The root `pyproject.toml` is the workspace — it declares path deps (`{ path = "...", develop = true }`) with no version constraint, so it never needs a version bump.

## Dependency Graph

```
ticketmaster (service)
  └── ticketmaster-libs (shared)
```

`ticketmaster` depends on `ticketmaster-libs` via a SemVer constraint (e.g. `ticketmaster-libs = "^0.0.1"`) in `src/ticketmaster/pyproject.toml`.

## Instructions

1. Read the `version` field from both pyprojects.
2. Read the `ticketmaster-libs` constraint from `src/ticketmaster/pyproject.toml`.
3. Display a table with columns: **Package**, **Version**, **ticketmaster-libs dep**.
4. Check for issues:
   - For 0.x versions, `^0.Y.Z` only matches `0.Y.*` (Poetry treats the first non-zero as the stability segment). Consumers MUST match the minor version of the shared package.
   - If `ticketmaster-libs` is at `0.Y.Z`, then `ticketmaster` must declare `ticketmaster-libs = "^0.Y.0"` (or `^0.Y.Z` where Z ≤ current).
   - For 1.x+ versions (`^X.Y.Z`), the constraint allows any `X.*`, so only major mismatches are flagged.
   - Flag any consumer whose constraint does not satisfy the current shared package version.
5. If the user asked to **bump**: ask which package to bump and by what level (patch/minor/major), then apply the changes.
   - After bumping `ticketmaster-libs`, check whether the new version is still covered by the existing `ticketmaster` constraint:
     - Covered (e.g. `0.0.1` → `0.0.2` with `^0.0.1`): no consumer change needed, but the service still needs a version bump if its own code changed (CI rule).
     - Not covered (e.g. `0.0.x` → `0.1.0` with `^0.0.1`): update the `ticketmaster-libs` constraint in `src/ticketmaster/pyproject.toml` to match, and bump `ticketmaster` at least at patch level because its pyproject changed.
6. After any version edits run `poetry lock --no-update` then `poetry install` from the project root. Do not hand-edit `pyproject.toml` fields other than `version` and dependency constraints.

## CI Enforcement Recap

`.github/workflows/on-pull-request.yaml::check_versions` fails the PR if:
- Code under `src/libs/` changed but `src/libs/pyproject.toml` version wasn't bumped.
- Code under `src/ticketmaster/` changed but `src/ticketmaster/pyproject.toml` version wasn't bumped.

Use this skill before opening a PR to make sure both constraints and versions are aligned.
