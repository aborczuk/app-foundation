---
description: Generate E2E testing pipeline artifacts (e2e.md + executable script) for the current feature based on design documents.
handoffs:
  - label: Run E2E Pipeline
    agent: speckit.e2e-run
    prompt: Run the E2E pipeline
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

This command generates two artifacts for end-to-end testing of a feature:

1. **`FEATURE_DIR/e2e.md`** — a structured E2E test plan with per-user-story sections and a final full-feature section
2. **`scripts/e2e_<feature-slug>.sh`** — an executable pipeline script that runs the E2E tests

The generated pipeline is **automation-first with human-assisted checkpoints only by exception**:
- Use automated checks (dry-run, log parsing, DB queries, API checks) whenever a deterministic oracle exists.
- Use interactive confirmation only where external state cannot be reliably asserted by the script alone (UI/external tools/manual approvals).
- Required human gates MUST block/fail in non-interactive mode; they MUST NOT auto-pass.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. Use shell quoting per CLAUDE.md "Shell Script Compatibility".

2. **Load design documents**: Read from FEATURE_DIR:
   - **Required**: spec.md (user stories), plan.md (tech stack, architecture, entrypoints)
   - **Required**: tasks.md (phases, checkpoints — needed to understand what each story delivers)
   - **Optional**: data-model.md (entities, DB tables), contracts/ (API specs, config schema), quickstart.md (integration scenarios)
   - If tasks.md does not exist, **STOP** and suggest running `/speckit.solution` first.

3. **Analyze the feature for E2E test requirements**:

   For each user story (from spec.md + tasks.md), identify:
   - **What observable behavior does this story produce?** (from the phase checkpoint in tasks.md)
   - **What external dependencies does it need?** (databases, APIs, services, hardware)
   - **What can be verified automatically?** (log events, DB state, exit codes, CLI output)
   - **What requires human verification?** (only when no reliable automated oracle exists)
   - **Why is human verification required?** (explicit reason per manual gate)
   - **What config or setup is needed?** (config files, env vars, running services)

   Also identify:
   - **Adopted dependencies**: External tools/packages listed under "Adopted dependencies" in spec.md. These MUST have E2E coverage — verify they are installed, configured, and return correct results for this project. An adopted dependency with no E2E section is a gap.
   - **Preflight checks**: Things that can be validated with `--dry-run` or equivalent (no side effects)
   - **Prerequisites**: External services, config files, env vars that must be in place
   - **Common blockers**: Known issues that could prevent E2E from passing (from quickstart.md or research.md)

4. **Generate `FEATURE_DIR/e2e.md`**: Pre-scaffold the E2E test plan from template:

   ```bash
   python .specify/scripts/pipeline-scaffold.py speckit.e2e --feature-dir $FEATURE_DIR \
     FEATURE_NAME="[Feature Name]" FEATURE_SLUG="[slug]"
   ```

   This copies `.specify/templates/e2e-template.md` to `$FEATURE_DIR/e2e.md` with:
   - Prerequisites section (external services, config files, env vars)
   - Recommended Pipeline section (full, preflight, run, verify, ci modes)
   - Section 1: Preflight (dry-run smoke test)
   - Sections 2+: User Story sections (with Purpose, External deps, Prerequisites checklist, Steps, Pass criteria)
   - Section Final: Full Feature E2E (orchestrates all stories)
   - Verification Commands section
   - Common Blockers section

5. **Generate `scripts/e2e_<feature-slug>.sh`**: Pre-scaffold the E2E execution script from template:

   ```bash
   python .specify/scripts/pipeline-scaffold.py speckit.e2e --feature-dir $FEATURE_DIR \
     FEATURE_NAME="[Feature Name]" FEATURE_SLUG="[slug]"
   ```

   This copies `.specify/templates/e2e-script-template.sh` to `scripts/e2e_[slug].sh` with:
   - Bash boilerplate (set -euo pipefail, config loading, cleanup trap)
   - Helper functions (usage, fail, log)
   - Placeholder functions for each E2E section (run_preflight, run_story_1, run_final)
   - Main dispatch logic (preflight/run/verify/ci/full modes)

   **Derive the slug** from the feature directory name (e.g., `001-auto-options-trader` → `e2e_001.sh` or a meaningful short name).

   **Script structure** (follow the pattern established by `scripts/e2e_paper.sh` if it exists):

   ```bash
   #!/usr/bin/env bash
   set -euo pipefail

   # Usage, config loading, utility functions
   # Subcommands: preflight | run | verify | full | ci
   # Per-section functions with:
   #   - Automated checks (log parsing, DB queries, exit codes)
   #   - Interactive prompts (read -r -p) only for non-automatable verification
   #   - Timestamp-gated assertions (verify events happened after phase start)
   #   - Temp config generation (never modify the user's live config)
   #   - Cleanup trap for temp files
   ```

   **Script requirements**:
   - **MUST** use `set -euo pipefail`
   - **MUST** clean up temp files via `trap cleanup EXIT`
   - **MUST** never modify the user's live config — generate temp configs
   - **MUST** support `read -r -p` prompts for required human verification steps
   - **MUST** fail/exit `blocked_manual` when a required human gate is reached in non-interactive mode
   - **MUST** validate external dependencies before attempting to use them
   - **MUST** use timestamp-gated assertions (verify events occurred after phase start, not from a previous run)
   - **MUST** include at least one executable automated pass/fail assertion per user-story section whenever a deterministic oracle exists
   - **MUST** fail a section when loop/lifecycle error signals appear (for example `"event loop is already running"` or pending-task destruction warnings)
   - **MUST** assert no orphan processes/tasks remain after each section's cleanup
   - **MUST** fail a section when live-vs-local state drift remains unresolved (for stateful integrations)
   - **MUST** include at least one deterministic state-safety assertion for stateful integrations (reconcile-before-decision evidence and no active orphan drift)
   - **MUST NOT** emit PASS when state transitions are logged without corresponding persisted lifecycle updates
   - **MUST** fail a section when local DB transactional writes leave partial commits or impossible lifecycle transitions
   - **MUST** include at least one deterministic transaction-integrity assertion for local DB mutation paths (atomic commit/rollback evidence and no partial-write residue)
   - **MUST NOT** emit PASS when persistence errors are swallowed or transaction outcomes are ambiguous
   - **MUST NOT** mark a section `PASS` if any automated gate failed
   - **MUST NOT** use a human gate as the only pass criterion when an automatable oracle exists
   - **MUST NOT** hardcode secrets, ports, or paths — read from config
   - **SHOULD** support `uv run` if available, fall back to `python3`
   - **SHOULD** provide a non-interactive mode (`ci`) for automation-only checks (preflight + verify)
   - **SHOULD** reuse patterns from existing E2E scripts in `scripts/` if they exist
   - Each section (user story) should be a separate function that can be called independently
   - The `full` subcommand runs all sections in order
   - The `run` subcommand runs the interactive sections (skipping preflight)
   - The `verify` subcommand prints verification commands and runs lightweight checks
   - The `preflight` subcommand runs dry-run validation only
   - The `ci` subcommand runs non-interactive automation checks only (no human-gated sections)

   Make the script executable: `chmod +x scripts/e2e_<slug>.sh`

6. **If an existing E2E script or e2e.md already exists**:
   - Read the existing artifacts first
   - **Ask the user**: "Existing E2E artifacts found. Should I regenerate from scratch or update the existing ones?"
   - If updating: preserve any manual customizations the user added, extend with new sections
   - If regenerating: replace entirely based on current design documents

7. **Report**: Output summary:
   - Path to generated e2e.md
   - Path to generated script
   - Number of E2E sections (per-story + final)
   - External dependencies identified
   - Which sections are fully automatable vs. human-assisted
   - Suggested first run: `scripts/e2e_<slug>.sh preflight <config>`

8. **Emit pipeline event**:
   
   Emit `e2e_generated` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "e2e_generated", "feature_id": "NNN", "phase": "solution", "e2e_artifact": "specs/NNN-feature/e2e.md", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

## Notes

- This command is a **generation** step — it creates artifacts but does not execute them. Use `/speckit.e2e-run` to execute.
- The generated script follows the same conventions as any existing `scripts/e2e_*.sh` in the repo.
- E2E artifacts live in the feature's spec directory (`FEATURE_DIR/e2e.md`) and scripts directory (`scripts/`).
- The pipeline is designed to be re-run after every significant change. Preflight (dry-run) is cheap; full runs require human time.
- Human verification is a last resort, not the default.
- Acceptance rule: unless the relevant E2E run passes, the feature/phase is not done.
- Never include actual secret values in generated artifacts. Reference env vars and config paths only.
