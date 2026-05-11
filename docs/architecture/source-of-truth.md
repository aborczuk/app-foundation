# Source Of Truth

Status: canonical
Last reviewed: 2026-05-09
Owner: repository architecture

## Purpose

This document resolves which files are authoritative when multiple docs mention the same workflow or subsystem.

## Canonical Sources

| Concern | Canonical source | Notes |
|---|---|---|
| Repo-specific agent rules | `AGENTS.md` | Highest-priority repo guidance for agents |
| Core governance principles | `constitution.md` | Quality gates and non-negotiables |
| Command registry and routing metadata | `command-manifest.yaml` | Repo-root manifest is canonical |
| Command behavior contracts | `.claude/commands/speckit.*.md` | Step-level contract docs |
| Runtime package maps | `docs/architecture/*.md` | Stable architecture maps |
| Workflow mechanics | `docs/architecture/workflow-overview.md`, `docs/governance/` | Read architecture doc first, then detailed governance docs |
| Feature-specific design intent | `specs/<feature-id>-*/` | Scoped to one feature, not repo-global architecture |

## Non-Canonical But Useful Sources

- `README.md`: onboarding summary
- `quickstart.md`: operator workflow quickstart
- feature handoff docs in `docs/governance/`: implementation context for specific migrations
- tests: executable truth for behavior, but not replacements for architecture docs

## Classification Rules

Use these labels at the top of major docs:

- `canonical`: the repo expects readers to trust this as the primary reference
- `derived`: summarized from canonical sources and should be updated when sources change
- `feature-specific`: scoped to one feature or migration
- `legacy`: preserved for history; do not extend without review

## Conflict Resolution

When two docs disagree:

1. Prefer the code if the disagreement is about current implementation.
2. Prefer the canonical source listed in this document.
3. Update the derived or stale document in the same change if practical.

