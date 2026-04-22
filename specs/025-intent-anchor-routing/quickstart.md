# Quickstart: Read-Code Anchor Output Simplification

## What This Feature Is

This feature makes `read-code` easier for agents to use by defaulting to a resolved anchor + bounded window output, exposing bounded ranked candidates only when explicitly requested, exposing inline body output only when explicitly requested, and documenting the read rules in `AGENTS.md`.

- Spec folder: [`specs/025-intent-anchor-routing/`](./)
- Task breakdown: [`tasks.md`](./tasks.md)

## How It Runs

Get the feature running locally in a few minutes.

### Prerequisites

- `uv`: check with `uv --version`
- Repository checkout: make sure you are at the repo root
- Read helper shell script: `scripts/read-code.sh`
- A populated codebase index: required for semantic retrieval and optional inline body output

### Installation

No new package or service is required for this feature. The implementation reuses the existing helper, vector index, and repository docs.

#### 1. Clone and set up environment

```bash
git clone <repo-url>
cd app-foundation
uv sync
```

#### 2. Confirm the read rules

```bash
sed -n '1,220p' AGENTS.md
```

The documented read rules should make the 125-line cap, helper-first reads, opt-in top-5 shortlist, fixed small-before/larger-after context split, and bounded candidate stepping easy to find.

### Run the Feature

```bash
source scripts/read-code.sh
read_code_context scripts/read_code.py "read_code_context" 125
read_code_context scripts/read_code.py "read_code_context" 125 --show-shortlist
read_code_context scripts/read_code.py "read_code_context" 125 --next-candidate
read_code_context scripts/read_code.py "read_code_context" 125 --inline-body
```

Expected behavior:

- The default helper output is the resolved anchor plus bounded window (no shortlist by default).
- `--show-shortlist` returns the ranked top-5 candidate list with confidence signals.
- `--next-candidate` (or `--candidate-index N`) selects another ranked candidate without forcing shortlist output.
- `context_lines` is a total budget with a fixed small-before/larger-after split (no optional override).
- Inline body output is opt-in via `--inline-body`.
- If `--inline-body` is set and the symbol body clears the `90/100` threshold, the body text is returned inline.
- If you need the body for a non-top candidate later, use the bounded follow-up helper path rather than inventing a wider command family.

### Smoke Test

Verify the feature contract is visible in the docs and helper output:

```bash
source scripts/read-code.sh
read_code_context scripts/read_code.py "read_code_context" 80
```

Expected:

- The default output is bounded context around the resolved symbol.
- Shortlist output appears only when requested.
- Candidate stepping works through `--next-candidate` / `--candidate-index N`.

For plan validation, run the Speckit plan gates:

```bash
uv run python scripts/speckit_gate_status.py --mode plan --feature-dir specs/025-intent-anchor-routing --json
uv run python scripts/speckit_plan_gate.py plan-sections --plan-file specs/025-intent-anchor-routing/plan.md --json
```

---

## What Was Done

This feature narrowed the read-code contract to four practical changes:

- document the read rules in `AGENTS.md`
- support explicit shortlist output and ranked candidate stepping
- require explicit request (`--inline-body`) before returning indexed body text
- allow a bounded follow-up helper path for non-top shortlist candidates
- widen retrieval recall with a bounded `top_k = 20`

- Detailed task breakdown: [`tasks.md`](./tasks.md)
- Implementation trail: feature branch `025-intent-anchor-routing`, commit `e1914c9`

### Decision Log

- Updated the quickstart to describe the shortlist/body contract, the `--inline-body` opt-in with `90/100` threshold, and the bounded follow-up helper so the feature matches the implemented read-code behavior.

---

## Common Issues

| Issue | Symptom | Fix |
|-------|---------|-----|
| Read helper still returns one anchor | Agent keeps retrying the same query | Confirm the shortlist/body-first behavior is implemented and documented. |
| Body payload missing | The helper falls back to a numeric window | Check that `--inline-body` was requested and the confidence clears the `90/100` cutoff. |
| Candidate list feels too small | The agent still needs repeated searches | Confirm retrieval is widened to `top_k = 20` and the visible shortlist is still capped at 5. |

---

## Next Steps

- Read the feature spec folder: [`specs/025-intent-anchor-routing/`](./)
- Read the implementation plan: [`plan.md`](./plan.md)
- Review the data model: [`data-model.md`](./data-model.md)
- Review the task breakdown: [`tasks.md`](./tasks.md)
- Run the plan review flow next: `/speckit.planreview`
