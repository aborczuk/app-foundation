---
description: Assemble prior art, patterns, and integration options for the current feature. Run before /speckit.plan - produces a compact research.md scaffold with all required sections.
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

Gather and record information only - no architecture decisions. Output a complete `research.md`
for the current feature that the `/speckit.plan` architecture agent will use to evaluate options.

## Outline

1. **Setup and scaffold first**:
   - Run `.specify/scripts/bash/setup-plan.sh --json` from repo root and parse the JSON output for `FEATURE_SPEC` and `FEATURE_DIR`.
   - Read the spec file at `FEATURE_SPEC` once to extract the feature's Functional Requirements list.
   - Cache those FR IDs and reuse the same list across every search pass in this command.
   - Immediately run:

     ```bash
     UV_CACHE_DIR="${TMPDIR:-/tmp}/app-foundation-uv-cache" uv run python .specify/scripts/pipeline-scaffold.py speckit.research --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"
     ```

   - This is the first step after setup so the compact scaffold exists before discovery begins.
   - The scaffold uses `.specify/templates/research-template-compact.md`, which is the compact research template for this command.

2. **Run one bounded research pass in the main agent**:
   - Do **not** spawn sub-agents.
   - Use the cached FR list once for all queries and keep each result set capped.
   - Keep outputs in tables, not prose.

   ### Code discovery
   - If a GitHub MCP server is configured, use it to search code and read the most relevant source files directly.
   - Also run GitHub CLI code searches for the major integration keywords from the spec.
   - Prefer repository-level matches when a reusable repo is more useful than a single file.
   - Cap results to the top 3-5 matches per query family.
   - For each repo/file found, record:
     - Source: `owner/repo` (URL)
     - File(s) to copy or adapt (specific path)
     - FRs it covers (map to FR-NNN from the spec)
     - Notes: copy as-is, adapt auth section, we maintain, etc.
     - Maintenance signal: last push date, stars (from `gh api repos/<owner>/<repo>` or GitHub MCP)

   ### Package adoption
   - Search PyPI, npm, and known SDK registries for the integration domain.
   - Use queries such as `"{integration} python library"`, `"{tool} sdk"`, and `"pip install {keyword}"`.
   - Cap results to the top 3-5 viable packages.
   - For each package found, MANDATORY installability verification:
     - PyPI: `pip index versions <package>` (Bash)
     - npm: `npm view <package>` (Bash)
     - GitHub: `gh api repos/<owner>/<repo>` (Bash)
   - If not installable from its claimed registry: record as REJECTED and skip to pattern reference.
   - For each viable package record: name, version, FRs covered, integration effort estimate.

   ### Conceptual patterns
   - Use WebSearch + WebFetch on top results for standard approaches experienced engineers already use.
   - Cap WebFetch to the top 3-5 results per query family.
   - For each approach found record:
     - The pattern name or description
     - Which FRs it appears to cover
     - Source URL
     - Whether it requires a custom server or not

3. **Synthesize and write `research.md`** with all required sections pre-structured:
   - The compact scaffold already exists from step 1.
   - Fill the existing tables and bullet lists with the capped results from step 2.
   - Keep the content concise and table-driven.

4. **Completion gate**:
   - Verify `research.md` contains all five required sections with substantive content.
   - If a section is thin, run one targeted follow-up search, then stop once that section is good enough.
   - Do **not** keep searching for marginal additions once each section has at least one solid candidate set.
   - An empty `## Repo Assembly Map` is only acceptable if it explicitly states:
     - `No relevant code repositories found after searching: [list of queries run]`.

5. **Emit pipeline event**:

   Emit `research_completed` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "research_completed", "feature_id": "NNN", "phase": "spec", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

6. **Report** to user: what was found in each section, which FRs are covered by existing
   sources, and which FRs will require net-new code. Then suggest running `/speckit.plan`.

## Local Validation

Run the smoke test to verify that the research scaffold wiring still matches the manifest and
command doc:

```bash
.specify/scripts/test-research.sh feature_id=XYZ
```

The harness checks the manifest template binding, the compact scaffold invocation documented in
this file, and the generated `research.md` section headers.

## Key rules

- This skill makes NO architecture decisions - it only presents what was found
- Do not spawn sub-agents for research; keep the work in one bounded main-agent pass.
- Do not run a clarification loop here; unresolved items become `Unanswered Questions` for plan.
- The 70% FR coverage threshold does NOT apply here - surface EVERYTHING, including partial matches
- Poor maintenance (old repo, few stars) is NOT a rejection reason for the Repo Assembly Map -
  record it with a maintenance note. The user decides whether to copy/adapt or not.
- Code on GitHub that is not published to a registry is still valid - a copied file is a valid adoption
- Installability verification applies ONLY to Package Adoption Options (Agent B)
- Keep discovery result sets capped and table-shaped rather than verbose prose.
- Pass the FR list once and reuse it for every query in this command.
- Record which search tools were used - this proves the search was done and enables debugging
