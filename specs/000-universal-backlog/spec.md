# Universal Backlog

## Purpose

Provide a repository-wide intake surface for ad-hoc work so backlog items can be recorded from any branch without depending on branch-local task files.

## User Story 1 - Route ad-hoc work into the universal backlog

As a contributor, I can add a task to the universal backlog from any branch, so requests are never blocked by a missing branch-local `tasks.md`.

### Acceptance Criteria

- `speckit.addtobacklog` resolves to `specs/000-universal-backlog/tasks.md` regardless of the current branch.
- The backlog directory exists in the repository and does not require bootstrap work before use.
- Backlog entries can be appended sequentially and estimated like any other task list.
