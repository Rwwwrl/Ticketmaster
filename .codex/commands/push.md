Push the current branch to remote.

Use the rules from `.codex/skills/push/SKILL.md`.

Hard rules:
- Never switch branches.
- Push only the current branch.

Steps:
1. Run `git branch --show-current`.
2. Run `git push -u origin HEAD`.
3. Report the result to the user.
