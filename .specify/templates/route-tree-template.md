---
source_path: "${SOURCE_PATH}"
source_kind: "${SOURCE_KIND}"
source_symbol: "${SOURCE_SYMBOL}"
generated_by: "generate_route_tree.py"
generated_at: "${GENERATED_AT}"
---

# Route Tree: ${TITLE}

## Route

- **Root router**: `CLAUDE.md`
- **Primary tool**: ${PRIMARY_TOOL}
- **Implementation**: ${IMPLEMENTATION}
- **Problem class**: ${PROBLEM_CLASS}
- **Why this route**: ${WHY_THIS_ROUTE}

## Progressive Load

1. **Root map**: read `CLAUDE.md` for the repo-wide routing rule.
2. **Task-local doc**: read the smallest artifact that matches the problem class.
3. **Anchored read**: use the route-specific helper to land on the exact file, section, or symbol.
4. **Implementation lookup**: read the implementation file when you need to inspect or modify the underlying logic.
5. **Verification**: confirm the change with the appropriate exact-check tool before marking the task done.

## How To

1. ${HOW_TO_STEP_1}
2. ${HOW_TO_STEP_2}
3. ${HOW_TO_STEP_3}

## Validation

- ${VALIDATION_1}
- ${VALIDATION_2}

## Notes

- ${NOTES_1}
- ${NOTES_2}
