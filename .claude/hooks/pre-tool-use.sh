#!/usr/bin/env bash
# PreToolUse guardrail (AGENTS.md §3): block direct push to main/master so a
# branch-protection violation is caught before it reaches the platform.
# Reads the tool-call JSON on stdin; denies a matching push, defers otherwise.
INPUT=$(cat)

if printf '%s' "$INPUT" \
  | grep -qE 'git[[:space:]]+push([[:space:]]+[^[:space:]]+)*[[:space:]]+(origin[[:space:]]+)?(main|master)\b'; then
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Direct push to main/master is blocked. Branch + open a PR (AGENTS.md §2)."}}'
  exit 0
fi

exit 0   # no match -> defer to the normal permission flow
