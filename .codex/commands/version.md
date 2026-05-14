Check or update Ticketmaster package versions.

Use the rules from `.codex/skills/version/SKILL.md`.

Steps:
1. Read versions from `src/libs/pyproject.toml` and `src/ticketmaster/pyproject.toml`.
2. Read the `ticketmaster-libs` dependency constraint from `src/ticketmaster/pyproject.toml`.
3. Report the package version table and any constraint mismatch.
4. If the user asked to bump versions, ask which package and bump level unless already specified.
5. After version edits, run `poetry lock --no-update` and `poetry install` from the project root.
