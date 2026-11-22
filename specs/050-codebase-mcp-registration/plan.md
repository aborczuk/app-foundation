# Combined Plan - 050-codebase-mcp-registration

_Feature: `050`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: xs
- risk_level: low
- reason: The requested Codex registrations and approval settings are absent from main.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "ops governance": "The change controls which code-intelligence tools Codex may invoke and the approval policy for those invocations."
    },
    "relevant": [
      "ops governance"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "low",
    "human_operator_dependency": "low",
    "overall": "low",
    "repo_uncertainty": "low",
    "requirement_clarity": "low",
    "runtime_side_effect_risk": "low",
    "state_data_migration_risk": "low"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": false,
    "expanded_design_notes": false,
    "external_research": false,
    "net_new_surface": false,
    "strategy_reason": "Repository evidence is sufficient for one small configuration slice; no new architecture, external research, or expanded design notes are needed."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [],
    "duplicate_reason": "The requested Codex registrations and approval settings are absent from main.",
    "risk_level": "low",
    "tshirt_size": "xs"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/validate_command_script_coverage.py`

### Term: codebase

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/src/mcp_codebase/server.py`

### Term: mcp

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/src/mcp_trello/server.py`

### Term: registration

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/cgc_owner.py`

### Term: branch

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/speckit_implement_step.py`

## Relevant Domains

### ops governance
- Why it matters: The change controls which code-intelligence tools Codex may invoke and the approval policy for those invocations.
- Required checklist prompts:
  - [x] A complete specification exists before implementation.
  - [x] The plan reuses existing MCP servers and commands.
  - [x] The versioned specification documents the change.
  - [x] An architecture flow diagram is not warranted for a declarative registration-only change.
  - [x] `.codex/config.toml` owns registrations and `AGENTS.md` owns language guidance.
  - [x] Existing tool documentation remains the operational reference.
  - [x] No critical system incident or on-call surface changes.
  - [x] No new escalation or communication path is needed.
  - [x] No architectural decision record is warranted for this low-risk configuration change.
  - [x] Configuration assertions provide the relevant verification feedback.
  - [x] No rule exception is required.

## Summary

Update the existing Codex configuration in one coherent slice: register the existing CodeGraph and codebase-LSP commands, make the two read-only Semble discovery tools automatic, preserve codebase-LSP diagnostics approval, and clarify the language preference in `AGENTS.md`.

## Internal Research

- `.codex/config.toml` already owns Semble's command, working directory, cache path, and tool-level approval settings.
- CodeGraphContext and codebase-LSP are existing repository capabilities with documented commands `uv run cgc mcp start` and `uv run python -m mcp_codebase`.
- The requested scope is declarative only; TOML parsing and targeted configuration assertions are sufficient verification.

## Design Slices

### Slice PL-01 - Register existing code-intelligence MCP services
- Estimate: low
- Implementation Directive: Update `.codex/config.toml` to retain all existing settings while setting Semble `search` and `find_related` to `auto`, adding the existing CodeGraph and codebase-LSP registrations, and retaining diagnostics approval; update the one technology-guidance sentence in `AGENTS.md`; add targeted TOML/config assertions.

## Plan Completion Summary

The low-risk, single-slice plan is sufficient because it reuses known commands and modifies only declarative configuration; tasking should create one implementation task with targeted parsing and configuration assertions.
