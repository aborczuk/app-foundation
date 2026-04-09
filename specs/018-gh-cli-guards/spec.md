# Feature Spec: GitHub CLI Payload Guardrails

## Summary

Add Bash-time guardrails to prevent high-payload GitHub CLI reads and route research usage
through bounded wrapper scripts.

## Scope

- Add a PreToolUse hook rule that denies risky `gh` read patterns (`gh pr diff`, broad read-style
  `gh api`, and heavy `gh pr view --json` fields).
- Provide low-payload wrappers for PR metadata and changed-file listing.
- Keep write-style `gh api -X POST|PATCH|PUT|DELETE` allowed for operational workflows.

## Out of Scope

- MCP-layer tool enforcement.
- Changes to GitHub repository permissions or network routing.
