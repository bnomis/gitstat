#!/bin/bash
# Populate the .agents submodule that .claude/rules, .claude/skills/* and the
# @.agents/claude/CLAUDE.md import point into. Cloud sessions clone without it.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

if [ -f .agents/claude/CLAUDE.md ]; then
  exit 0
fi

git submodule update --init .agents >&2

# Rules and imports are read when the session starts, possibly before this
# hook ran, so tell the session to read them now. SessionStart stdout is added
# to the session's context.
echo 'The .agents submodule was empty when this session started and has just been initialised, so the shared rules may not be loaded. Before doing anything else, read .agents/claude/CLAUDE.md and every file in .agents/claude/rules/ (including python/), and follow them.'
