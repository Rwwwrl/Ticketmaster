Create a new git branch from the current conversation context.

Use the rules from `.codex/skills/branch/SKILL.md`.

Hard rules:
- Do not reset, stash, rebase, stage, commit, or push.
- Use the user's branch name or type verbatim when provided.
- If the task context is too thin to name the branch confidently, ask for a one-line description.

Steps:
1. Run `git status` and `git branch --show-current`.
2. Choose a branch name in the `<type>/<short-description>` format.
3. Tell the user the branch name before creating it.
4. Run `git checkout -b <name>` from the current HEAD.
5. Report the new branch name.
