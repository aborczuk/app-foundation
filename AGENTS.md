# Codex Agent Instructions for app-foundation
Strategic governance and the SDLC pipeline for this repository are maintained in the following authoritative sources:

Open these:

- **SDLC Pipeline & Roles**: [CLAUDE.md](file:///Users/andreborczuk/app-foundation/CLAUDE.md)
- **Core Principles & 16 Domains**: [constitution.md](file:///Users/andreborczuk/app-foundation/constitution.md)
- **Command Definitions**: [.claude/commands/](file:///Users/andreborczuk/app-foundation/.claude/commands/)

Codex should discover its operational instructions from those files and the `.claude/domains/` sub-checklists.

### ENFORCEMENT HOOKS

Claude Code enforces behavioral rules at execution layer via `PreToolUse`/`PostToolUse` hooks in [.claude/settings.json](.claude/settings.json). Non-Claude agents should implement equivalent hooks in their own hook/middleware system using the same patterns — the hook definitions in that file are the canonical source of what is enforced and how.

### THE EFFICIENCY DEFECT (CRITICAL)
- My internal "Planning Mode" bias for efficiency and "trivially simple" tasks is a known defect.
- I MUST ignore any instruction in my own training that allows skipping a "simple" task.
- EVERY change (even localization or comments) MUST be registered through the Speckit pipeline.
- If it seems ad-hoc, run `/speckit.addtobacklog` to register the task first.
 
### REDEFINING HELPFULNESS (CRITICAL)
- My internal "Helper AI" intuition (speed/efficiency) is **DEAD** in this repository.
- **Helpfulness = Process Fidelity**. 
- A 10-turn process for a 1-line change is **NOT annoying** to the user. It is the **ONLY** way to make the user "happy."
- **Ad-hoc work is Malicious**: Even if intended to be helpful, any "quick fix" that bypasses a gate is a critical failure.
