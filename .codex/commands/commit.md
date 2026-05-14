Create a commit for staged changes.

Use the rules from `.codex/skills/commit/SKILL.md`.

Hard rules:
- Only commit when this command is explicitly invoked.
- Commit only what the user already staged.
- Never stage files on behalf of the user.
- Do not include `Co-Authored-By` lines.

Steps:
1. Run `git status` and `git diff --staged`.
2. If nothing is staged, stop and tell the user.
3. If staged changes cover unrelated concerns, split commits by concern.
4. Use the Ticketmaster commit format: `[scope] <type> <context> <description>`.
5. Run `git commit -m "<message>"`.
