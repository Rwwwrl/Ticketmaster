# Codex Configuration

This directory contains project-local Codex configuration for Ticketmaster.

## Files

- `config.toml` defines project-local Codex runtime settings.
- `rules/default.rules` defines project-local command prefix approvals.
- `../AGENTS.md` is the repo-level instruction file Codex reads for ongoing work.
- `commands/` contains direct command prompts for explicit workflows.
- `skills/` contains project workflows and task-specific guidance.

## Skill Usage

Project skills are intentionally kept in the repo so they can be versioned with
the codebase. When a task matches a skill, read the matching
`.codex/skills/<name>/SKILL.md` before making changes.
