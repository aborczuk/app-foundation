# Research: [FEATURE NAME]

Investigation of prior art, integration patterns, and existing code/packages that could reduce scope.

---

## Zero-Custom-Server Assessment

What no-server integration options exist? For each, which FRs does it cover?

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| [Option 1] | [FR list] | [Brief explanation] | [Uncovered FR list] |

---

## Repo Assembly Map

Assemble pieces from multiple repositories to cover all FRs. Each row = one repo/file that covers one or more FRs.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| [owner/repo] | [path/to/file] | [FR list] | [Integration notes] |

**After assembly**: which FRs remain uncovered and require net-new code?
- [FR-XXX]: [reason no existing code covers it]

---

## Package Adoption Options

Installable packages only (verified via `pip index versions`, `npm view`, or `gh api repos/`). Unverified entries belong in Repo Assembly Map.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| [package] | [version] | [FR list] | [1-5: low to high] | [PyPI/npm/GitHub verified] |

---

## Conceptual Patterns

Non-code synthesis from web research. Standard approaches, common patterns, known mistakes.

- **Pattern**: [name] — [description] — covers: [FRs] — requires custom server: yes/no
  - Source: [URL]

---

## Search Tools Used

Log which tools and queries ran. Used to diagnose shallow results in future debugging.

- Agent A (Code Discovery): [GitHub MCP search / WebFetch on repo URLs / gh search code]
- Agent B (Package Discovery): [pip index versions / npm view / WebSearch]
- Agent C (Conceptual Patterns): [WebSearch queries / WebFetch on N URLs]

---

## Unanswered Questions

Anything still unknown after all research. These become [NEEDS CLARIFICATION] in plan.md.

- [Question 1]
- [Question 2]
