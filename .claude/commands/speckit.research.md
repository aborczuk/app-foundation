---
description: Assemble prior art, patterns, and integration options for the current feature. Run before /speckit.plan — produces research.md with all required sections.
model: sonnet
handoffs:
  - label: Build Technical Plan
    agent: speckit.plan
    prompt: Research is complete. Build the technical plan.
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Gather and record information only — no architecture decisions. Output a complete `research.md`
for the current feature that the `/speckit.plan` architecture agent will use to evaluate options.

## Outline

1. **Setup**: Run `.specify/scripts/bash/setup-plan.sh --json` from repo root and parse JSON for
   FEATURE_SPEC, SPECS_DIR, FEATURE_DIR. Read FEATURE_SPEC to extract the feature's Functional
   Requirements list — this list drives all three search agents.

2. **Run THREE parallel research sub-agents** (launch all three at the same time):

   ### Agent A — Code search (what exists in copyable/runnable form)

   Goal: find repositories and files whose code addresses one or more FRs from the spec.
   The model is ASSEMBLY — multiple repos each covering different FRs combine into a solution.

   Search strategy (use ALL applicable):
   - If the GitHub MCP server is configured (`github` in MCP server list):
     - `search_code` for key integration terms from the spec
     - `get_file_contents` to read the most relevant source files directly
     - `get_repository` to capture stars and last-push date
   - Always also run: `gh search code "{keyword}" --language=python` (via Bash) for each
     major integration keyword from the spec
   - `gh search repos "{term}" --topic {topic}` for integration-specific repos
   - WebFetch on README and key source files from the most promising repos

   For EACH repo/file found, record:
   - Source: `owner/repo` (URL)
   - File(s) to copy or adapt (specific path)
   - FRs it covers (map to FR-NNN from the spec)
   - Notes: copy as-is, adapt auth section, we maintain, etc.
   - Maintenance signal: last push date, stars (from `gh api repos/<owner>/<repo>` or GitHub MCP)

   ### Agent B — Package adoption (what can be installed from a registry)

   Goal: find installable packages that cover one or more FRs.

   Search strategy:
   - WebSearch: PyPI, npm, and known SDK registries for the integration domain
   - Queries: `"{integration} python library"`, `"{tool} sdk"`, `"pip install {keyword}"`

   For EACH package found, MANDATORY installability verification:
   - PyPI: `pip index versions <package>` (Bash)
   - npm: `npm view <package>` (Bash)
   - GitHub: `gh api repos/<owner>/<repo>` (Bash)
   - If not installable from its claimed registry: record as REJECTED, skip to pattern reference

   For each viable package record: name, version, FRs covered, integration effort estimate.

   ### Agent C — Conceptual search (how people connect these things — not code)

   Goal: find the STANDARD approaches that experienced engineers already know. This is the
   "Perplexity-style" search — synthesized answers from non-code sources.

   Search strategy (WebSearch + WebFetch on top results):
   - `"how to connect {source system} to {target system}"`
   - `"{source} {target} integration without server"`
   - `"{source} {target} webhook guide"`
   - `"{integration domain} best practice"`
   - `site:reddit.com "{source} {target}"`
   - `site:stackoverflow.com "{integration} trigger"`
   - `"{source system} github actions"` (for automation features)
   - `"{target system} n8n workflow"` (for n8n-based features)
   - `"{source} zapier"` / `"{source} make.com"` (for no-server options)

   WebFetch the top 3–5 results to read full content (not just titles).

   For each approach found record:
   - The pattern name or description
   - Which FRs it appears to cover
   - Source URL
   - Whether it requires a custom server or not

3. **Synthesize and write `research.md`** with all required sections pre-structured:

   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.research --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
      - Reads `.specify/command-manifest.yaml` to resolve which artifacts speckit.research owns
      - Copies `.specify/templates/research-template.md` to `$FEATURE_DIR/research.md`
      - Pre-structures the file with 5 required sections (headers, table schemas) ready for LLM to populate

   2. The research.md is now scaffolded with all required sections:
      - Zero-Custom-Server Assessment: table for no-code integration options
      - Repo Assembly Map: table for repositories with reusable code (MANDATORY even if empty)
      - Package Adoption Options: table for installable packages (verified only)
      - Conceptual Patterns: non-code synthesis from web research — patterns and sources
      - Search Tools Used: audit trail of which discovery methods ran
      - Unanswered Questions: clarifications that become [NEEDS CLARIFICATION] in plan

4. **Completion gate**: Verify research.md contains all five required sections with substantive
   content (not just empty tables). If any section is empty, run a targeted follow-up search
   before completing. An empty `## Repo Assembly Map` is only acceptable if it explicitly states
   "No relevant code repositories found after searching: [list of queries run]".

5. **Emit pipeline event**:
   
   Emit `research_completed` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "research_completed", "feature_id": "NNN", "phase": "spec", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

6. **Report** to user: what was found in each section, which FRs are covered by existing
   sources, and which FRs will require net-new code. Then suggest running `/speckit.plan`.

## Key rules

- This skill makes NO architecture decisions — it only presents what was found
- The 70% FR coverage threshold does NOT apply here — surface EVERYTHING, including partial matches
- Poor maintenance (old repo, few stars) is NOT a rejection reason for the Repo Assembly Map —
  record it with a maintenance note. The user decides whether to copy/adapt or not.
- Code on GitHub that is not published to a registry is still valid — a copied file is valid adoption
- Installability verification applies ONLY to Package Adoption Options (Agent B)
- Record which search tools were used — this proves the search was done and enables debugging
