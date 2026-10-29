# gitstat

Visualisation and report of statistics from github.com for a user, a repo or an organisation.

## Shared rules and skills

Shared rules and skills come from the [agents](https://github.com/bnomis/agents)
repository, a git submodule at `.agents/`:

- `.claude/rules` links to `.agents/claude/rules`
- `.claude/skills/*` link to `.agents/claude/skills/*`

@.agents/claude/CLAUDE.md

After cloning: `git submodule update --init`. Claude Code cloud sessions do this in the SessionStart hook (`.claude/hooks/session-start.sh`). To update the shared set:
`git submodule update --remote .agents`, then commit the new pointer.

Project-specific rules and skills go in this repository's own `claude/`
directory, not in agents (see `.agents/claude/rules/rule-scope.md`).
