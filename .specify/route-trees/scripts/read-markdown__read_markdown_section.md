---
source_path: "scripts/read-markdown.sh"
source_kind: "script"
source_symbol: "read_markdown_section"
generated_by: "generate_route_tree.py"
generated_at: "2026-04-16T16:28:02Z"
---

# Route Tree: read-markdown.read_markdown_section (script)

## Route

- **Root router**: `CLAUDE.md`
- **Primary tool**: scripts/read-markdown.sh
- **Implementation**: scripts/read_markdown.py
- **Problem class**: documentation navigation and workflow routing
- **Why this route**: The source is best understood by anchoring the exact file or symbol first, then expanding only when the question needs broader relationships.

## Progressive Load

1. **Root map**: read `CLAUDE.md` for the repo-wide routing rule.
2. **Task-local doc**: read the smallest artifact that matches the problem class.
3. **Anchored read**: use the route-specific helper to land on the exact file, section, or symbol.
4. **Implementation lookup**: read the implementation file when you need to inspect or modify the underlying logic.
5. **Verification**: confirm the change with the appropriate exact-check tool before marking the task done.

## How To

1. Run `scripts/read-markdown.sh` against the source path to anchor the exact location.
2. Use `scripts/read_markdown.py` if you need to inspect or modify the underlying logic.
3. Read only the smallest bounded window or section needed to complete the change.

## Validation

- Confirm the selected anchor is in the expected file, section, or symbol span.
- Run the repo's exact verifier before marking the task complete.

## Notes

- Keep the route tree small and task-specific.
- Treat this artifact as the progressive-load companion to the source file or command.
